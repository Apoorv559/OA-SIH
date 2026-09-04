"""
ESP32 Sensor Data Simulator.

Simulates realistic sensor data from the OA monitoring wearable
and streams it to the backend via WebSocket.

Usage:
    python simulate_esp32.py [--host localhost] [--port 8000]
"""

import asyncio
import json
import math
import random
import time
import argparse

try:
    import websockets
except ImportError:
    print("Installing websockets...")
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets"])
    import websockets


class WalkingSimulator:
    """Simulates realistic walking gait sensor data."""

    def __init__(self):
        self.time = 0.0
        self.step_freq = 1.8  # Steps per second (~108 steps/min)
        self.phase = 0.0

    def update(self, dt: float):
        self.time += dt
        self.phase = (self.time * self.step_freq * 2 * math.pi)

    def get_imu(self, segment: str, side: str) -> dict:
        """Generate IMU data for a specific body segment."""
        # Base gravity
        az = 9.81

        # Phase offset between left and right (180° out of phase)
        offset = 0 if side == "left" else math.pi

        if segment == "thigh":
            # Thigh swings back and forth during gait
            ax = 2.0 * math.sin(self.phase + offset) + random.gauss(0, 0.1)
            ay = 0.5 * math.cos(self.phase * 2 + offset) + random.gauss(0, 0.05)
            az += 1.0 * abs(math.sin(self.phase + offset)) + random.gauss(0, 0.1)
            gx = 80.0 * math.cos(self.phase + offset) + random.gauss(0, 2)
            gy = 10.0 * math.sin(self.phase * 2 + offset) + random.gauss(0, 1)
            gz = 5.0 * math.sin(self.phase + offset) + random.gauss(0, 1)
        else:  # shin
            # Shin has more dynamic movement (whip-like)
            ax = 3.5 * math.sin(self.phase + offset + 0.3) + random.gauss(0, 0.15)
            ay = 0.8 * math.cos(self.phase * 2 + offset) + random.gauss(0, 0.08)
            az += 2.0 * abs(math.sin(self.phase + offset + 0.3)) + random.gauss(0, 0.15)
            gx = 120.0 * math.cos(self.phase + offset + 0.3) + random.gauss(0, 3)
            gy = 15.0 * math.sin(self.phase * 2 + offset) + random.gauss(0, 2)
            gz = 8.0 * math.sin(self.phase + offset) + random.gauss(0, 1.5)

        return {
            "ax": round(ax, 2),
            "ay": round(ay, 2),
            "az": round(az, 2),
            "gx": round(gx, 2),
            "gy": round(gy, 2),
            "gz": round(gz, 2),
        }

    def get_flex(self, side: str) -> float:
        """Generate flex sensor reading (knee bend angle)."""
        offset = 0 if side == "left" else math.pi
        # During walking, knee flexes ~15-60 degrees cyclically
        angle = 35 + 25 * math.sin(self.phase + offset) + random.gauss(0, 1.5)
        return round(max(0, min(180, angle)), 1)

    def get_fsr(self, side: str) -> dict:
        """Generate FSR pressure values for one foot."""
        offset = 0 if side == "left" else math.pi
        phase = self.phase + offset

        # Heel strike phase
        heel_active = max(0, math.sin(phase))
        # Toe-off phase (delayed)
        toe_active = max(0, math.sin(phase - 1.0))

        # Base pressure + gait cycle modulation
        heel = int(max(0, 800 * heel_active + random.gauss(100, 40)))
        toe = int(max(0, 600 * toe_active + random.gauss(80, 30)))
        outer = int(max(0, 300 * (heel_active * 0.5 + toe_active * 0.3) + random.gauss(50, 20)))
        inner = int(max(0, 350 * (heel_active * 0.6 + toe_active * 0.4) + random.gauss(60, 25)))

        return {
            "heel": min(heel, 4095),
            "toe": min(toe, 4095),
            "outer": min(outer, 4095),
            "inner": min(inner, 4095),
        }

    def generate_frame(self, timestamp_ms: int) -> dict:
        """Generate a complete sensor frame."""
        return {
            "ts": timestamp_ms,
            "imu": {
                "left_thigh": self.get_imu("thigh", "left"),
                "right_thigh": self.get_imu("thigh", "right"),
                "left_shin": self.get_imu("shin", "left"),
                "right_shin": self.get_imu("shin", "right"),
            },
            "flex": {
                "left_knee": self.get_flex("left"),
                "right_knee": self.get_flex("right"),
            },
            "fsr": {
                "left_foot": self.get_fsr("left"),
                "right_foot": self.get_fsr("right"),
            },
            "buttons": {
                "btn1": False,
                "btn2": False,
                "btn3": False,
            }
        }


async def simulate(host: str, port: int):
    """Main simulation loop."""
    uri = f"ws://{host}:{port}/ws/sensor-data"
    sim = WalkingSimulator()
    dt = 0.02  # 50 Hz

    print(f"\n{'='*55}")
    print(f"  ESP32 Sensor Simulator")
    print(f"  Streaming to: {uri}")
    print(f"  Frequency: {1/dt:.0f} Hz")
    print(f"{'='*55}\n")

    while True:
        try:
            async with websockets.connect(uri) as ws:
                print("[✓] Connected to backend server")
                start_time = time.time()
                frame_count = 0

                while True:
                    sim.update(dt)
                    ts = int((time.time() - start_time) * 1000)
                    frame = sim.generate_frame(ts)

                    await ws.send(json.dumps(frame))

                    # Check for incoming messages (alerts from server)
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=0.001)
                        cmd = json.loads(msg)
                        if cmd.get("alert"):
                            print(f"  ⚠️  ALERT received from server!")
                        if cmd.get("buzzer"):
                            print(f"  🔔 Buzzer command: {cmd['buzzer']} beeps")
                    except asyncio.TimeoutError:
                        pass

                    frame_count += 1
                    if frame_count % 250 == 0:  # Every 5 seconds
                        elapsed = time.time() - start_time
                        print(f"  [{elapsed:.0f}s] Sent {frame_count} frames "
                              f"| Knee L:{frame['flex']['left_knee']}° R:{frame['flex']['right_knee']}° "
                              f"| FSR L:{frame['fsr']['left_foot']['heel']} R:{frame['fsr']['right_foot']['heel']}")

                    await asyncio.sleep(dt)

        except ConnectionRefusedError:
            print("[✗] Cannot connect to backend. Retrying in 3s...")
            await asyncio.sleep(3)
        except websockets.exceptions.ConnectionClosed:
            print("[!] Connection closed. Reconnecting in 2s...")
            await asyncio.sleep(2)
        except KeyboardInterrupt:
            print("\n[Stop] Simulator stopped.")
            break


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ESP32 Sensor Simulator")
    parser.add_argument("--host", default="localhost", help="Backend host")
    parser.add_argument("--port", type=int, default=8000, help="Backend port")
    args = parser.parse_args()

    try:
        asyncio.run(simulate(args.host, args.port))
    except KeyboardInterrupt:
        print("\nSimulator stopped.")
