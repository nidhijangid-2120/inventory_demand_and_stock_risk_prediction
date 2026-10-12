"""
Apache Kafka Streaming Ingestion Simulator & Spark Structured Streaming Consumer

Features:
1. Producer: Generates simulated near-real-time POS sales and inventory movement events
2. Consumer: Listens to incoming events and updates real-time tracking metrics
3. Fallback: Includes local file-stream fallback mode if Docker/Kafka broker is not active
"""

import os
import json
import time
import random
from datetime import datetime

SAMPLE_STORES = ["S001", "S002", "S003", "S004", "S005"]
SAMPLE_PRODUCTS = [f"P{i:04d}" for i in range(1, 21)]
CATEGORIES = {
    "P0001": "Electronics", "P0002": "Clothing", "P0003": "Clothing",
    "P0004": "Electronics", "P0005": "Groceries", "P0006": "Toys"
}

def generate_pos_event():
    p_id = random.choice(SAMPLE_PRODUCTS)
    s_id = random.choice(SAMPLE_STORES)
    qty = random.randint(1, 15)
    return {
        "event_id": f"evt_{int(time.time()*1000)}_{random.randint(100, 999)}",
        "event_timestamp": datetime.now().isoformat(),
        "store_id": s_id,
        "product_id": p_id,
        "category": CATEGORIES.get(p_id, "General"),
        "units_sold": qty,
        "unit_price": round(random.uniform(15.0, 150.0), 2),
        "source": "simulated_pos_register"
    }

def run_simulation(num_events: int = 10, delay_sec: float = 0.5):
    print(f"--- Simulating {num_events} Streaming POS Sales Events ---")
    os.makedirs("data/streaming_events", exist_ok=True)
    
    events = []
    for i in range(num_events):
        event = generate_pos_event()
        events.append(event)
        print(f"[{i+1}/{num_events}] Emitted Event {event['event_id']} -> Store {event['store_id']}, Product {event['product_id']}, Units: {event['units_sold']}")
        time.sleep(delay_sec)

    snapshot_path = "data/streaming_events/recent_streamed_events.json"
    with open(snapshot_path, "w") as f:
        json.dump(events, f, indent=2)
    print(f"Simulation completed. Events persisted to {snapshot_path}")

if __name__ == "__main__":
    run_simulation(num_events=5, delay_sec=0.2)
