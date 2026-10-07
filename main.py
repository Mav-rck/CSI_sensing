from fastapi import FastAPI, Request
from prometheus_client import make_asgi_app, Gauge
import numpy as np

app = FastAPI()

# Mount Prometheus metrics endpoint at /metrics
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# Define Prometheus Gauges
csi_variance_metric = Gauge('csi_variance', 'Variance of CSI amplitude')
csi_mean_metric = Gauge('csi_mean', 'Mean of CSI amplitude')
csi_ptp_metric = Gauge('csi_peak_to_peak', 'Peak-to-Peak of CSI amplitude')

@app.post("/ingest")
async def ingest_csi(request: Request):
    """Endpoint to receive raw CSI arrays from the local serial forwarder."""
    payload = await request.json()
    amplitudes = payload.get("csi_data", [])
    
    if amplitudes and len(amplitudes) > 0:
        csi_array = np.array(amplitudes)
        
        # Compute Metrics in the cloud
        variance = np.var(csi_array)
        mean = np.mean(csi_array)
        ptp = np.ptp(csi_array)
        
        # Update Prometheus Gauges
        csi_variance_metric.set(variance)
        csi_mean_metric.set(mean)
        csi_ptp_metric.set(ptp)
        
        return {"status": "success", "variance": variance}
    
    return {"status": "empty payload"}
