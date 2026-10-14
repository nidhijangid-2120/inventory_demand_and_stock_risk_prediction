"""Run an uploaded CSV through the full pipeline without replacing the base run."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
import shutil
import sys
import tempfile
import uuid
from collections import Counter, defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.common.spark_utils import get_spark_session
from src.features.build_features import build_gold_features
from src.forecasting.train_forecasting import train_and_evaluate
from src.processing.ingest_and_clean import run_bronze_ingestion, run_silver_cleaning
from src.risk.generate_risk_snapshot import generate_risk_recommendations


EXPECTED_COLUMNS = [
    "Date", "Store ID", "Product ID", "Category", "Region",
    "Inventory Level", "Units Sold", "Units Ordered", "Price", "Discount",
    "Weather Condition", "Promotion", "Competitor Pricing", "Seasonality",
    "Epidemic", "Demand",
]
INTEGER_COLUMNS = [
    "Inventory Level", "Units Sold", "Units Ordered", "Discount",
    "Promotion", "Epidemic", "Demand",
]
FLOAT_COLUMNS = ["Price", "Competitor Pricing"]


def validate_dataset(path: Path) -> tuple[int, int, str, str]:
    row_count = 0
    dates: set[str] = set()
    pair_counts: Counter[tuple[str, str]] = Counter()
    pair_dates: dict[tuple[str, str], set[str]] = defaultdict(set)
    try:
        source = path.open("r", encoding="utf-8-sig", newline="")
    except OSError as exc:
        raise ValueError(f"Could not read uploaded CSV: {exc}") from exc

    with source:
        reader = csv.DictReader(source)
        if reader.fieldnames != EXPECTED_COLUMNS:
            missing = [c for c in EXPECTED_COLUMNS if c not in (reader.fieldnames or [])]
            extra = [c for c in (reader.fieldnames or []) if c not in EXPECTED_COLUMNS]
            detail = []
            if missing:
                detail.append("missing: " + ", ".join(missing))
            if extra:
                detail.append("unexpected: " + ", ".join(extra))
            raise ValueError("CSV columns must match the 16 project columns in the same order (" + "; ".join(detail) + ").")

        for line_number, row in enumerate(reader, start=2):
            if None in row or any(row.get(c) is None for c in EXPECTED_COLUMNS):
                raise ValueError(f"CSV row {line_number} does not contain all 16 fields.")
            try:
                date_value = dt.date.fromisoformat(row["Date"].strip())
            except (ValueError, AttributeError) as exc:
                raise ValueError(f"CSV row {line_number} has an invalid Date; use YYYY-MM-DD.") from exc
            for column in INTEGER_COLUMNS:
                try:
                    int(row[column])
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"CSV row {line_number} has a non-integer value in {column}.") from exc
            for column in FLOAT_COLUMNS:
                try:
                    value = float(row[column])
                    if not math.isfinite(value):
                        raise ValueError
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"CSV row {line_number} has an invalid number in {column}.") from exc
            if not row["Store ID"].strip() or not row["Product ID"].strip():
                raise ValueError(f"CSV row {line_number} needs both Store ID and Product ID.")
            row_count += 1
            dates.add(date_value.isoformat())
            pair = (row["Store ID"].strip(), row["Product ID"].strip())
            pair_counts[pair] += 1
            pair_dates[pair].add(date_value.isoformat())

    if not row_count:
        raise ValueError("The uploaded CSV has a header but no data rows.")
    if len(dates) < 90:
        raise ValueError(f"The dataset has {len(dates)} distinct dates; at least 90 are needed for reliable time-based training/evaluation.")
    short_pairs = [key for key in pair_counts if len(pair_dates[key]) < 36]
    if short_pairs:
        sample = ", ".join(f"{store}/{product} ({len(pair_dates[(store, product)])} dates)" for store, product in short_pairs[:5])
        raise ValueError("Each store/product series needs at least 36 rows for 28-day history features. Short examples: " + sample)

    return row_count, len(dates), min(dates), max(dates)


def configure_java_runtime() -> None:
    """Prefer a real JDK over Windows' Oracle javapath redirector."""
    configured_home = os.environ.get("JAVA_HOME")
    if configured_home and (Path(configured_home) / "bin" / "java.exe").is_file():
        java_bin = str(Path(configured_home) / "bin")
        os.environ["PATH"] = java_bin + os.pathsep + os.environ.get("PATH", "")
        return

    candidates = []
    for path_entry in os.environ.get("PATH", "").split(os.pathsep):
        if not path_entry:
            continue
        candidate = Path(path_entry) / "java.exe"
        if candidate.is_file() and "javapath" not in str(candidate).lower():
            candidates.append(candidate)
    jdk = next((candidate for candidate in candidates if "jdk" in candidate.parent.parent.name.lower()), None)
    if jdk:
        java_home = jdk.parent.parent
        os.environ["JAVA_HOME"] = str(java_home)
        os.environ["PATH"] = str(jdk.parent) + os.pathsep + os.environ.get("PATH", "")


def run(input_csv: Path) -> dict:
    row_count, date_count, first_date, last_date = validate_dataset(input_csv)
    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    run_relative = Path("data") / "processed" / "retraining_runs" / f"run_{run_id}"
    run_dir = PROJECT_ROOT / run_relative
    run_dir.mkdir(parents=True, exist_ok=False)

    uploaded_copy = run_dir / "uploaded_sales_data.csv"
    shutil.copy2(input_csv, uploaded_copy)
    spark_tmp = run_dir / "spark_tmp"
    spark_tmp.mkdir(parents=True, exist_ok=True)
    # Keep Spark/JVM temporary files inside the run folder. This also avoids
    # Windows profiles where Python's default TEMP directory is not writable.
    os.environ["TEMP"] = str(spark_tmp)
    os.environ["TMP"] = str(spark_tmp)
    os.environ["TMPDIR"] = str(spark_tmp)
    os.environ["SPARK_LOCAL_DIRS"] = str(spark_tmp)
    tempfile.tempdir = str(spark_tmp)
    configure_java_runtime()
    bronze = run_dir / "bronze"
    silver = run_dir / "silver"
    gold = run_dir / "gold"
    model = run_dir / "rf_demand_model"
    metrics = run_dir / "model_metrics.json"
    snapshot = run_dir / "risk_snapshot.json"

    spark = get_spark_session(f"inventory-retrain-{run_id}")
    try:
        print(f"Validated {row_count:,} rows across {date_count:,} dates ({first_date} to {last_date}).", flush=True)
        print("STEP 1/4: Ingesting and preparing Bronze/Silver data…", flush=True)
        bronze_df = run_bronze_ingestion(spark, str(uploaded_copy), str(bronze))
        run_silver_cleaning(spark, str(bronze), str(silver))
        del bronze_df

        print("STEP 2/4: Building time-series features…", flush=True)
        build_gold_features(spark, str(silver), str(gold))

        print("STEP 3/4: Training and evaluating the demand model…", flush=True)
        train_and_evaluate(spark, str(gold), str(model), str(metrics))

        print("STEP 4/4: Scoring current inventory risks…", flush=True)
        results = generate_risk_recommendations(spark, str(gold), str(model), str(snapshot))
        if not results:
            raise RuntimeError("Risk scoring completed but returned no store/product results.")
    finally:
        spark.stop()

    metadata = {
        "run_id": run_id,
        "dataset_name": input_csv.name,
        "row_count": row_count,
        "date_count": date_count,
        "first_date": first_date,
        "last_date": last_date,
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "run_dir": run_relative.as_posix(),
        "sales_path": (run_relative / "uploaded_sales_data.csv").as_posix(),
        "gold_path": (run_relative / "gold").as_posix(),
        "model_path": (run_relative / "rf_demand_model").as_posix(),
        "metrics_path": (run_relative / "model_metrics.json").as_posix(),
        "snapshot_path": (run_relative / "risk_snapshot.json").as_posix(),
        "snapshot_date": results[0].get("snapshot_date"),
        "sku_count": len(results),
    }

    # The dashboard switches runs only after every pipeline stage has succeeded.
    active_file = PROJECT_ROOT / "data" / "processed" / "active_retraining_run.json"
    temp_file = active_file.with_suffix(".tmp")
    with temp_file.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    os.replace(temp_file, active_file)
    print(f"RETRAINING_COMPLETE: {json.dumps(metadata)}", flush=True)
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description="Retrain the inventory demand model on an uploaded CSV.")
    parser.add_argument("--input-csv", required=True, help="CSV to ingest and train from")
    args = parser.parse_args()
    metadata = run(Path(args.input_csv).resolve())
    print(f"Active dashboard snapshot: {metadata['snapshot_date']} ({metadata['sku_count']} store/product rows)")


if __name__ == "__main__":
    main()
