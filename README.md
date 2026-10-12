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

Evaluated using chronological time-based splits (Train: 70% | Validation: 17% | Test: 14%):

| Model / Approach | Horizon | Validation MAE | Validation RMSE | Validation WAPE | Test MAE | Test WAPE |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Naive Lag 1 Baseline** | 7 Days | 236.24 | 308.36 | 30.56% | - | - |
| **Rolling 7-Day Average Baseline** | 7 Days | 132.40 | 171.71 | 17.13% | - | - |
| **Spark MLlib Random Forest Model** | **7 Days** | **97.81** | **129.77** | **12.65%** | **103.07** | **14.46%** |

The machine learning model cuts forecasting error by more than **58%** compared to naive baselines.

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

### 6. Launch Streamlit Operations Dashboard
```bash
streamlit run src/dashboard/app.py
```
View the dashboard at `http://localhost:8501`.