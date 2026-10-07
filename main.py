import os
import time
import uvicorn
import numpy as np
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List
from collections import deque

# --- Configuration ---
MOTION_THRESHOLD = float(os.environ.get("MOTION_THRESHOLD", 50.0))
MAX_DATA_POINTS = 500  # Stores the last 500 readings in memory

app = FastAPI(title="ESP32 CSI Cloud Math Engine - No DB")

# In-memory circular buffer (automatically drops oldest data when full)
historical_data = deque(maxlen=MAX_DATA_POINTS)

# --- Pydantic Models for JSON Validation ---
class CSIFrame(BaseModel):
    rssi: int
    payload: List[int]

class CSIBatch(BaseModel):
    room_id: str
    frames: List[CSIFrame]

# --- The Math Engine Worker ---
def process_csi_math(batch: CSIBatch):
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
        
        # 2. Inference Logic
        activity_state = "walking" if variance > MOTION_THRESHOLD else "empty"
        
        # 3. Store data locally instead of pushing to an external DB
        data_point = {
            "timestamp": int(time.time() * 1000), # JS expects milliseconds
            "room_id": batch.room_id,
            "variance": round(variance, 2),
            "rssi": frame.rssi,
            "state": activity_state
        }
        
        historical_data.append(data_point)

# --- API Endpoints ---
@app.post("/api/csi")
async def receive_csi_data(batch: CSIBatch, background_tasks: BackgroundTasks):
    # Process the math in the background so the ESP32 gets an instant response
    background_tasks.add_task(process_csi_math, batch)
    return {"status": "success", "message": f"Queued {len(batch.frames)} frames"}

@app.get("/api/metrics")
def get_metrics():
    # Returns the historical data as JSON (Can be consumed by Grafana's Infinity plugin)
    return list(historical_data)

@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    # A lightweight, self-contained HTML dashboard using Chart.js
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Live CSI Occupancy</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            body { font-family: sans-serif; padding: 20px; background: #121212; color: white; }
            .status { font-size: 2em; font-weight: bold; margin-bottom: 20px; }
            .walking { color: #4caf50; }
            .empty { color: #9e9e9e; }
        </style>
    </head>
    <body>
        <h2>Room Status: <span id="status-text" class="status empty">Waiting for data...</span></h2>
        <div><canvas id="varianceChart" width="400" height="150"></canvas></div>

        <script>
            const ctx = document.getElementById('varianceChart').getContext('2d');
            const chart = new Chart(ctx, {
                type: 'line',
                data: { labels: [], datasets: [{ label: 'CSI Variance', data: [], borderColor: '#2196f3', tension: 0.2 }] },
                options: { animation: false, scales: { x: { display: false }, y: { beginAtZero: true } } }
            });

            async function fetchData() {
                const response = await fetch('/api/metrics');
                const data = await response.json();
                
                if (data.length > 0) {
                    const latest = data[data.length - 1];
                    
                    // Update Status Text
                    const statusEl = document.getElementById('status-text');
                    statusEl.innerText = latest.state.toUpperCase();
                    statusEl.className = `status ${latest.state}`;
                    
                    // Update Chart
                    chart.data.labels = data.map(d => d.timestamp);
                    chart.data.datasets[0].data = data.map(d => d.variance);
                    chart.update();
                }
            }
            // Poll the API every 1 second
            setInterval(fetchData, 1000);
        </script>
    </body>
    </html>
    """

if __name__ == "__main__":
    # Render routes traffic to 0.0.0.0 and assigns the port dynamically
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)