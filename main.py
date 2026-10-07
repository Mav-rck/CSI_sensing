import os
import time
import uvicorn
import numpy as np
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from typing import List
from collections import deque

app = FastAPI(title="CSI Variance & Inference Engine")

# In-memory buffer keeping the last 1000 data points for Grafana
db_buffer = deque(maxlen=1000)

# Set the motion threshold via Render environment variables (Defaults to 50.0)
MOTION_THRESHOLD = float(os.environ.get("MOTION_THRESHOLD", 50.0))

# --- Pydantic Data Models (Matches the edge_relay.py payload) ---
class CSIFrame(BaseModel):
    rssi: int
    payload: List[int]

class CSIBatch(BaseModel):
    room_id: str
    frames: List[CSIFrame]

# --- Mathematical Processing ---
def compute_variance(batch: CSIBatch):
    for frame in batch.frames:
        # Convert list to numpy array
        csi_array = np.array(frame.payload, dtype=int)
        
        # Ensure array is perfectly paired (Real, Imaginary)
        if len(csi_array) % 2 != 0:
            continue
            
        real = csi_array[0::2]
        imag = csi_array[1::2]
        
        # Calculate Amplitude: sqrt(R^2 + I^2)
        amplitude = np.sqrt(real**2 + imag**2)
        
        # Calculate statistical variance across all subcarriers
        variance = float(np.var(amplitude))
        
        # Inference condition
        state = "walking" if variance > MOTION_THRESHOLD else "empty"
        
        # Store processed metric in the circular buffer
        db_buffer.append({
            "timestamp": int(time.time() * 1000), 
            "room_id": batch.room_id,
            "variance": round(variance, 2),
            "rssi": frame.rssi,
            "state": state
        })

# --- Cloud API Endpoints ---
@app.post("/api/csi")
async def ingest_csi(batch: CSIBatch, bg_tasks: BackgroundTasks):
    # Delegate math to the background so the PC relay gets an instant 200 OK response
    bg_tasks.add_task(compute_variance, batch)
    return {"status": "success", "processed": len(batch.frames)}

@app.get("/api/metrics")
def expose_metrics_to_grafana():
    # Grafana's Infinity plugin will poll this endpoint to build the dashboard
    return list(db_buffer)

if __name__ == "__main__":
    # Render assigns the active port dynamically via the PORT environment variable
    port = int(os.environ.get("PORT", 8000))
    # Binding to 0.0.0.0 is mandatory for Render to route external traffic
    uvicorn.run(app, host="0.0.0.0", port=port)
