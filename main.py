import os
import uvicorn
import numpy as np
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List
import influxdb_client
from influxdb_client.client.write_api import SYNCHRONOUS

# --- Environment Variables (Set these in Render Dashboard) ---
INFLUX_URL = os.environ.get("INFLUX_URL", "https://us-east-1-1.aws.cloud2.influxdata.com")
INFLUX_TOKEN = os.environ.get("INFLUX_TOKEN")
INFLUX_ORG = os.environ.get("INFLUX_ORG")
INFLUX_BUCKET = os.environ.get("INFLUX_BUCKET", "csi_data")
MOTION_THRESHOLD = float(os.environ.get("MOTION_THRESHOLD", 50.0))

app = FastAPI(title="ESP32 CSI Cloud Math Engine")

# --- Pydantic Models for JSON Validation ---
class CSIFrame(BaseModel):
    rssi: int
    payload: List[int]  # The raw I/Q array: [Real, Imag, Real, Imag...]

class CSIBatch(BaseModel):
    room_id: str
    frames: List[CSIFrame]

# --- The Math Engine & Database Worker ---
def process_and_store(batch: CSIBatch):
    # Connect to InfluxDB
    client = influxdb_client.InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    write_api = client.write_api(write_options=SYNCHRONOUS)

    try:
        # Process each batched packet sent by the ESP32
        for frame in batch.frames:
            csi_int = np.array(frame.payload, dtype=int)
            
            # Ensure the payload has even pairs (Real and Imaginary)
            if len(csi_int) % 2 != 0:
                continue
                
            real = csi_int[0::2]
            imag = csi_int[1::2]
            
            # 1. NumPy Math Engine
            amplitude = np.sqrt(real**2 + imag**2)
            variance = float(np.var(amplitude))
            
            # 2. Cloud Inference Logic
            activity_state = "walking" if variance > MOTION_THRESHOLD else "empty"
            presence = 1 if variance > MOTION_THRESHOLD else 0

            # 3. Push to InfluxDB
            point = influxdb_client.Point("room_occupancy") \
                .tag("room_id", batch.room_id) \
                .field("presence_detected", presence) \
                .field("activity_type", activity_state) \
                .field("csi_variance", variance) \
                .field("rssi", float(frame.rssi))

            write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
    finally:
        client.close()

# --- API Endpoints ---
@app.post("/api/csi")
async def receive_csi_data(batch: CSIBatch, background_tasks: BackgroundTasks):
    if not INFLUX_TOKEN:
        raise HTTPException(status_code=500, detail="InfluxDB credentials missing on server")
    
    # Offload the heavy math and DB push to the background
    background_tasks.add_task(process_and_store, batch)
    
    return {"status": "success", "message": f"Queued {len(batch.frames)} CSI frames for processing"}

@app.get("/health")
def health_check():
    return {"status": "healthy", "message": "Math engine is running"}

if __name__ == "__main__":
    # Render assigns a dynamic port via the PORT environment variable
    port = int(os.environ.get("PORT", 8000))
    # Binding to 0.0.0.0 is strictly required for Render to route traffic
    uvicorn.run(app, host="0.0.0.0", port=port)