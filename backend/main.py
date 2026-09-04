from fastapi import FastAPI, HTTPException, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import tempfile
import shutil
import json
import asyncio
from movement_analysis import analyze_video
from edge_processing import BiomechanicalProcessor
from pydantic import BaseModel
import pandas as pd
import joblib
import os

app = FastAPI(title="OA Risk Score Predictor API")

# Setup CORS for the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load the model
model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'model.pkl')
model = None

@app.on_event("startup")
def load_model():
    global model
    try:
        model = joblib.load(model_path)
        print("Model loaded successfully.")
    except Exception as e:
        print(f"Error loading model: {e}. Make sure to run train_dummy_model.py first.")

class UserProfile(BaseModel):
    Age: float
    Sex: str
    Height: float
    Weight: float
    BMI: float
    Previous_injury: str
    Surgery: str
    Family_history: str
    Occupation: str
    Physical_activity: str
    Pain: float
    Morning_stiffness: str
    Functional_limitations: str
    Relevant_comorbidities: str

@app.post("/predict")
def predict_risk(profile: UserProfile):
    if model is None:
        raise HTTPException(status_code=500, detail="Model is not loaded.")
    
    # Convert Pydantic model to DataFrame
    input_df = pd.DataFrame([profile.dict()])
    
    try:
        # Predict
        prediction = model.predict(input_df)
        
        # Depending on the model, we can also get probabilities
        try:
            proba = model.predict_proba(input_df)
            probabilities = {cls: float(p) for cls, p in zip(model.classes_, proba[0])}
        except:
            probabilities = {}
            
        return {
            "prediction": prediction[0],
            "probabilities": probabilities
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def read_root():
    return {"message": "Welcome to OA Risk Score Predictor API"}

@app.post("/api/analyze-movement")
async def analyze_movement(
    video: UploadFile = File(...),
    movement_type: str = Form("Squat")
):
    try:
        # Create a temporary file to save the uploaded video
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_video:
            shutil.copyfileobj(video.file, temp_video)
            temp_video_path = temp_video.name
            
        # Analyze the video using our movement_analysis module
        results = analyze_video(temp_video_path, movement_type)
        
        # Clean up the temporary file
        os.remove(temp_video_path)
        
        if "error" in results:
            raise HTTPException(status_code=400, detail=results["error"])
            
        return results
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========================== WEBSOCKET INFRASTRUCTURE ==========================

class ConnectionManager:
    """Manages WebSocket connections for both ESP32 devices and browser clients."""

    def __init__(self):
        self.esp32_connection: WebSocket | None = None
        self.browser_clients: list[WebSocket] = []
        self.processor = BiomechanicalProcessor()

    async def connect_esp32(self, websocket: WebSocket):
        await websocket.accept()
        self.esp32_connection = websocket
        print("[WS] ESP32 device connected")

    async def connect_browser(self, websocket: WebSocket):
        await websocket.accept()
        self.browser_clients.append(websocket)
        print(f"[WS] Browser client connected ({len(self.browser_clients)} total)")

    def disconnect_esp32(self):
        self.esp32_connection = None
        print("[WS] ESP32 device disconnected")

    def disconnect_browser(self, websocket: WebSocket):
        if websocket in self.browser_clients:
            self.browser_clients.remove(websocket)
        print(f"[WS] Browser client disconnected ({len(self.browser_clients)} remaining)")

    async def broadcast_to_browsers(self, data: dict):
        """Send processed data to all connected browser clients."""
        if not self.browser_clients:
            return
        message = json.dumps(data)
        disconnected = []
        for client in self.browser_clients:
            try:
                await client.send_text(message)
            except Exception:
                disconnected.append(client)
        for client in disconnected:
            self.disconnect_browser(client)

    async def send_to_esp32(self, data: dict):
        """Send a command back to the ESP32 (e.g., buzzer/LED alerts)."""
        if self.esp32_connection:
            try:
                await self.esp32_connection.send_text(json.dumps(data))
            except Exception:
                self.disconnect_esp32()


manager = ConnectionManager()


# ========================== WEBSOCKET ENDPOINTS ==========================

@app.websocket("/ws/sensor-data")
async def ws_sensor_data(websocket: WebSocket):
    """
    WebSocket endpoint for the ESP32 device.
    Receives raw sensor JSON at ~50Hz, processes it through the
    biomechanical engine, and broadcasts results to browser clients.
    """
    await manager.connect_esp32(websocket)
    try:
        while True:
            # Receive raw sensor data from ESP32
            raw_text = await websocket.receive_text()
            raw_data = json.loads(raw_text)

            # Run edge processing
            features = manager.processor.process(raw_data)

            # Check if we need to send an alert back to ESP32
            if features.alert:
                await manager.send_to_esp32({
                    "alert": True,
                    "buzzer": 1,
                    "led": [1, 0, 0]
                })

            # Broadcast processed features to all browser clients
            await manager.broadcast_to_browsers(features.to_dict())

    except WebSocketDisconnect:
        manager.disconnect_esp32()
    except Exception as e:
        print(f"[WS] ESP32 connection error: {e}")
        manager.disconnect_esp32()


@app.websocket("/ws/dashboard")
async def ws_dashboard(websocket: WebSocket):
    """
    WebSocket endpoint for browser dashboard clients.
    Receives processed biomechanical features in real-time.
    Also supports requesting summaries via messages.
    """
    await manager.connect_browser(websocket)
    try:
        while True:
            # Listen for messages from the browser (e.g., requesting summary)
            message = await websocket.receive_text()
            try:
                cmd = json.loads(message)
                if cmd.get("action") == "get_summary":
                    summary = manager.processor.get_summary()
                    await websocket.send_text(json.dumps({"type": "summary", "data": summary}))
                elif cmd.get("action") == "reset_steps":
                    manager.processor.step_count = 0
                    manager.processor.step_timestamps.clear()
                    await websocket.send_text(json.dumps({"type": "info", "message": "Step count reset"}))
            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        manager.disconnect_browser(websocket)
    except Exception as e:
        print(f"[WS] Browser client error: {e}")
        manager.disconnect_browser(websocket)


@app.get("/api/sensor-status")
def sensor_status():
    """REST endpoint to check if the ESP32 is connected and get current metrics."""
    connected = manager.esp32_connection is not None
    summary = manager.processor.get_summary() if connected else {}
    return {
        "esp32_connected": connected,
        "browser_clients": len(manager.browser_clients),
        "summary": summary
    }
