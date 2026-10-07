import serial
import requests
import threading
import time

# --- Configuration ---
SERIAL_PORT = 'COM6'  # Update to your ESP32's port (e.g., /dev/ttyUSB0 for Linux)
BAUD_RATE = 921600
RENDER_API_URL = "https://csi-zxh1.onrender.com/api/csi" # Update with your Render URL
BATCH_SIZE = 25       # Send 25 CSI packets per cloud request to optimize bandwidth

def send_to_cloud(payload):
    """Sends the batched JSON payload to Render in a background thread."""
    try:
        # 5-second timeout prevents hanging threads if the cloud goes offline
        response = requests.post(RENDER_API_URL, json=payload, timeout=5)
        if response.status_code == 200:
            print(f"[{time.strftime('%H:%M:%S')}] Success: Pushed {len(payload['frames'])} raw frames to Render.")
        else:
            print(f"[{time.strftime('%H:%M:%S')}] Server Error: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"Network error - Render unreachable: {e}")

# --- Initialize Serial Connection ---
try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    print(f"Listening on {SERIAL_PORT}. Forwarding raw CSI data to {RENDER_API_URL}...")
except Exception as e:
    print(f"Fatal Error: Could not open {SERIAL_PORT}. {e}")
    exit()

current_batch = []

while True:
    try:
        # Read and decode the serial line
        line = ser.readline().decode('utf-8').strip()
        
        # Validate the packet structure matches the ESP32 output
        if line.startswith("CSI_START") and line.endswith("CSI_END"):
            parts = line.split(',')
            
            # Ensure the packet hasn't been severely truncated
            if len(parts) < 4:
                continue
                
            rssi = int(parts[1])
            data_len = int(parts[2])
            raw_payload = parts[3:-1]
            
            # Ensure payload length matches the expected length to prevent index errors in the cloud
            if len(raw_payload) != data_len:
                continue
                
            # Convert string array to integers for standard JSON serialization
            int_payload = [int(x) for x in raw_payload]
            
            # Append the raw frame to the memory buffer
            current_batch.append({
                "rssi": rssi,
                "payload": int_payload
            })
            
            # Dispatch the payload to Render once the batch limit is reached
            if len(current_batch) >= BATCH_SIZE:
                batch_payload = {
                    "room_id": "living_room",
                    "frames": current_batch
                }
                
                # Execute the HTTP POST in a thread so the script can immediately return to reading serial data
                threading.Thread(target=send_to_cloud, args=(batch_payload,)).start()
                
                # Clear the buffer for the next batch
                current_batch = []
                
    except ValueError:
        # Silently ignore serial collisions or characters that fail integer conversion
        pass
    except KeyboardInterrupt:
        print("\nClosing serial connection and exiting.")
        ser.close()
        break