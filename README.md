# AI Inventory Demand & Stock Risk Prediction System

An end-to-end, production-oriented Data Engineering and Machine Learning platform that connects historical sales and demand forecasting to automated stock risk identification and replenishment decisions.

---

## 🏗️ Architecture & Medallion Pipeline

```
[Raw CSV: 76,000 Rows]
        │
        ▼
[Bronze Layer (Parquet)] ➔ Schema validation & ingestion metadata
        │
        ▼
[Silver Layer (Parquet)] ➔ Cleaned, deduplicated, standardized types & constraints
        │
        ▼
[Gold Layer (Parquet)]   ➔ Leakage-free feature engineering (Lags 1/7/14/28, Rolling 7/14/28, 7-Day Target)
        │
        ├───────────────────────────────────┐
        ▼                                   ▼
[Spark MLlib Demand Forecaster]      [Deterministic Stock Risk Engine]
(Trained RandomForest Pipeline)      (Calculates Gaps, Days of Cover & Actions)
        │                                   │
        └─────────────────┬─────────────────┘
                          ▼
            [FastAPI Backend & Streamlit UI]
```

---

## 📊 Model Performance & Baseline Benchmark

Evaluated using chronological 70% / 15% / 15% date cutoffs, with seven observations removed at each boundary so a seven-day target cannot cross into the next split:

| Model / Approach | Horizon | Validation MAE | Validation RMSE | Validation WAPE | Test MAE | Test WAPE |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Naive Lag 1 Baseline** | 7 Days | 239.41 | 311.62 | 29.63% | - | - |
| **Rolling 7-Day Average Baseline** | 7 Days | 125.63 | 163.51 | 15.55% | - | - |
| **Spark MLlib Random Forest Model** | **7 Days** | **90.91** | **121.15** | **11.25%** | **103.83** | **14.97%** |

On this evaluation, the model reduces WAPE by about **62%** versus the naive baseline and **28%** versus the rolling-average baseline.

---

## 🚀 Running the Project

### 1. Run Data Ingestion & Medallion Processing
```bash
python src/processing/ingest_and_clean.py
```

### 2. Run Leakage-Free Feature Engineering
```bash
python src/features/build_features.py
```

### 3. Train Spark MLlib Forecaster & Benchmarks
```bash
python src/forecasting/train_forecasting.py
```

### 4. Generate Latest Inventory Risk Snapshot
```bash
python src/risk/generate_risk_snapshot.py
```

### 5. Launch FastAPI Backend Service
```bash
uvicorn src.api.main:app --reload --port 8000
```
Interactive API documentation available at `http://localhost:8000/docs`.

### Sales and stock operations
The dashboard's **Sales & stock** tab records sales, supplier purchase orders, and received deliveries through FastAPI. The API persists them in a local SQLite operations database, seeds starting inventory and daily sales history from the active project snapshot and CSV, and recalculates seven-day demand and stock risk from the latest 28 recorded sales days (falling back to the saved ML forecast when no sales history exists). Endpoints are listed at `http://localhost:8000/docs`; the main operations routes are `GET /operations/risks`, `GET /operations/inventory`, `POST /operations/sales`, `POST /operations/orders`, and `POST /operations/receipts`. CSV uploads in **Model & data** run the complete Spark training pipeline through `POST /upload-sales`.

### 6. Launch Streamlit Operations Dashboard
```bash
streamlit run src/dashboard/app.py
```
View the dashboard at `http://localhost:8501`.

To retrain from the dashboard, open **Model & data**, upload a CSV with the same 16 columns and order as `data/raw/sales_data.csv`, then click **Retrain model and update dashboard**. The upload needs at least 90 distinct dates and 36 consecutive daily records per store/product series, with no duplicate date/store/product rows. Each run is stored separately; the dashboard switches to it only after ingestion, feature engineering, training, and risk scoring all succeed. The original CSV and last successful model/results are retained.
