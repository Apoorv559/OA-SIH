"""
Edge Processing Module for Real-Time Biomechanical Feature Extraction.

Receives raw sensor data from the ESP32 wearable and computes:
- Joint kinematics (knee angles from thigh/shin IMUs + flex sensors)
- Gait phase detection (heel-strike / toe-off from FSRs)
- Load distribution & asymmetry analysis
- Step counting
"""

import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional


# ========================== DATA STRUCTURES ==========================

@dataclass
class Vec3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def magnitude(self) -> float:
        return math.sqrt(self.x**2 + self.y**2 + self.z**2)


@dataclass
class IMUReading:
    accel: Vec3 = field(default_factory=Vec3)
    gyro: Vec3 = field(default_factory=Vec3)


@dataclass
class FootPressure:
    heel: int = 0
    toe: int = 0
    outer: int = 0
    inner: int = 0

    def total(self) -> int:
        return self.heel + self.toe + self.outer + self.inner

    def center_of_pressure(self) -> tuple:
        """Returns (x, y) center of pressure as ratio. x: heel(-1) to toe(+1), y: inner(-1) to outer(+1)."""
        total = max(self.total(), 1)
        x = (self.toe - self.heel) / total
        y = (self.outer - self.inner) / total
        return (x, y)


@dataclass
class SensorFrame:
    """Single frame of all sensor data from the ESP32."""
    timestamp: int = 0
    imu_left_thigh: IMUReading = field(default_factory=IMUReading)
    imu_right_thigh: IMUReading = field(default_factory=IMUReading)
    imu_left_shin: IMUReading = field(default_factory=IMUReading)
    imu_right_shin: IMUReading = field(default_factory=IMUReading)
    flex_left_knee: float = 0.0
    flex_right_knee: float = 0.0
    fsr_left_foot: FootPressure = field(default_factory=FootPressure)
    fsr_right_foot: FootPressure = field(default_factory=FootPressure)


@dataclass
class BiomechanicalFeatures:
    """Computed biomechanical features for each frame."""
    timestamp: int = 0

    # Joint Angles (degrees)
    left_knee_angle: float = 0.0
    right_knee_angle: float = 0.0
    left_knee_angular_velocity: float = 0.0
    right_knee_angular_velocity: float = 0.0

    # Gait
    gait_phase_left: str = "unknown"    # "stance", "swing", "heel_strike", "toe_off"
    gait_phase_right: str = "unknown"
    step_count: int = 0
    cadence: float = 0.0               # steps per minute
    stride_time: float = 0.0           # seconds

    # Load Distribution
    left_foot_load: int = 0
    right_foot_load: int = 0
    load_asymmetry: float = 0.0        # 0 = symmetric, 1 = fully asymmetric
    left_cop: tuple = (0.0, 0.0)
    right_cop: tuple = (0.0, 0.0)

    # Accelerometer magnitudes (for activity level)
    left_thigh_accel_mag: float = 0.0
    right_thigh_accel_mag: float = 0.0
    left_shin_accel_mag: float = 0.0
    right_shin_accel_mag: float = 0.0

    # Alerts
    alert: bool = False
    alert_message: str = ""

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "joint_angles": {
                "left_knee": round(self.left_knee_angle, 1),
                "right_knee": round(self.right_knee_angle, 1),
                "left_knee_velocity": round(self.left_knee_angular_velocity, 1),
                "right_knee_velocity": round(self.right_knee_angular_velocity, 1),
            },
            "gait": {
                "phase_left": self.gait_phase_left,
                "phase_right": self.gait_phase_right,
                "step_count": self.step_count,
                "cadence": round(self.cadence, 1),
                "stride_time": round(self.stride_time, 3),
            },
            "pressure": {
                "left_foot_load": self.left_foot_load,
                "right_foot_load": self.right_foot_load,
                "load_asymmetry": round(self.load_asymmetry, 3),
                "left_cop": [round(c, 3) for c in self.left_cop],
                "right_cop": [round(c, 3) for c in self.right_cop],
            },
            "activity": {
                "left_thigh": round(self.left_thigh_accel_mag, 2),
                "right_thigh": round(self.right_thigh_accel_mag, 2),
                "left_shin": round(self.left_shin_accel_mag, 2),
                "right_shin": round(self.right_shin_accel_mag, 2),
            },
            "alert": {
                "active": self.alert,
                "message": self.alert_message,
            }
        }


# ========================== LOW-PASS FILTER ==========================

class ExponentialMovingAverage:
    """Simple EMA filter for smoothing noisy sensor data."""

    def __init__(self, alpha: float = 0.3):
        self.alpha = alpha
        self.value: Optional[float] = None

    def update(self, raw: float) -> float:
        if self.value is None:
            self.value = raw
        else:
            self.value = self.alpha * raw + (1 - self.alpha) * self.value
        return self.value

    def reset(self):
        self.value = None


# ========================== GAIT PHASE DETECTOR ==========================

class GaitPhaseDetector:
    """Detects gait phases using FSR thresholding."""

    def __init__(self, threshold: int = 200):
        self.threshold = threshold
        self.prev_heel_on = False
        self.prev_toe_on = False
        self.phase = "unknown"

    def update(self, foot: FootPressure) -> str:
        heel_on = foot.heel > self.threshold
        toe_on = foot.toe > self.threshold

        if heel_on and not self.prev_heel_on:
            self.phase = "heel_strike"
        elif heel_on and toe_on:
            self.phase = "stance"
        elif toe_on and not heel_on and self.prev_heel_on:
            self.phase = "toe_off"
        elif not heel_on and not toe_on:
            self.phase = "swing"

        self.prev_heel_on = heel_on
        self.prev_toe_on = toe_on
        return self.phase


# ========================== MAIN PROCESSOR ==========================

class BiomechanicalProcessor:
    """
    Main edge-processing engine.
    Call `process(raw_json)` for each incoming sensor frame.
    """

    # Thresholds for alerts
    KNEE_ANGLE_MAX = 160.0      # Alert if knee hyperextends
    LOAD_ASYMMETRY_WARN = 0.35  # Warn if > 35% asymmetric
    FSR_THRESHOLD = 200         # Min FSR value to count as "loaded"

    def __init__(self):
        # Filters for each knee angle
        self.filter_left_knee = ExponentialMovingAverage(alpha=0.4)
        self.filter_right_knee = ExponentialMovingAverage(alpha=0.4)

        # Gait detectors
        self.gait_left = GaitPhaseDetector(threshold=self.FSR_THRESHOLD)
        self.gait_right = GaitPhaseDetector(threshold=self.FSR_THRESHOLD)

        # Step counting
        self.step_count = 0
        self.last_step_time = 0.0
        self.step_timestamps = deque(maxlen=20)  # For cadence calc

        # Previous knee angles for velocity
        self.prev_left_knee = 0.0
        self.prev_right_knee = 0.0
        self.prev_timestamp = 0

        # History buffer for advanced features
        self.history: deque = deque(maxlen=500)  # ~10 seconds at 50Hz

    def parse_frame(self, data: dict) -> SensorFrame:
        """Parse raw JSON from ESP32 into a SensorFrame."""
        frame = SensorFrame()
        frame.timestamp = data.get("ts", 0)

        imu = data.get("imu", {})
        for key, attr in [
            ("left_thigh", "imu_left_thigh"),
            ("right_thigh", "imu_right_thigh"),
            ("left_shin", "imu_left_shin"),
            ("right_shin", "imu_right_shin"),
        ]:
            raw = imu.get(key, {})
            reading = IMUReading(
                accel=Vec3(raw.get("ax", 0), raw.get("ay", 0), raw.get("az", 0)),
                gyro=Vec3(raw.get("gx", 0), raw.get("gy", 0), raw.get("gz", 0)),
            )
            setattr(frame, attr, reading)

        flex = data.get("flex", {})
        frame.flex_left_knee = flex.get("left_knee", 0.0)
        frame.flex_right_knee = flex.get("right_knee", 0.0)

        fsr = data.get("fsr", {})
        for key, attr in [("left_foot", "fsr_left_foot"), ("right_foot", "fsr_right_foot")]:
            raw = fsr.get(key, {})
            setattr(frame, attr, FootPressure(
                heel=raw.get("heel", 0),
                toe=raw.get("toe", 0),
                outer=raw.get("outer", 0),
                inner=raw.get("inner", 0),
            ))

        return frame

    def compute_knee_angle_from_imu(self, thigh: IMUReading, shin: IMUReading) -> float:
        """
        Estimate knee angle from the relative pitch between thigh and shin IMUs.
        Uses accelerometer-based tilt estimation.
        """
        # Pitch angle of thigh segment (angle relative to gravity)
        thigh_pitch = math.atan2(thigh.accel.x, 
            math.sqrt(thigh.accel.y**2 + thigh.accel.z**2))
        # Pitch angle of shin segment
        shin_pitch = math.atan2(shin.accel.x, 
            math.sqrt(shin.accel.y**2 + shin.accel.z**2))

        # Knee angle = relative angle between thigh and shin
        knee_angle = abs(math.degrees(thigh_pitch - shin_pitch))

        # Normalize to 0-180 range
        knee_angle = max(0, min(180, knee_angle))
        return knee_angle

    def fuse_knee_angle(self, imu_angle: float, flex_angle: float, alpha: float = 0.6) -> float:
        """
        Fuse IMU-derived knee angle with flex sensor reading.
        Uses weighted average with IMU having slightly more weight.
        """
        if flex_angle <= 0:
            return imu_angle
        return alpha * imu_angle + (1 - alpha) * flex_angle

    def process(self, raw_data: dict) -> BiomechanicalFeatures:
        """
        Main processing pipeline. Takes raw JSON from ESP32, returns computed features.
        """
        frame = self.parse_frame(raw_data)
        features = BiomechanicalFeatures()
        features.timestamp = frame.timestamp

        # --- 1. JOINT KINEMATICS ---
        # Compute knee angles from IMU
        imu_left_knee = self.compute_knee_angle_from_imu(
            frame.imu_left_thigh, frame.imu_left_shin)
        imu_right_knee = self.compute_knee_angle_from_imu(
            frame.imu_right_thigh, frame.imu_right_shin)

        # Fuse with flex sensor
        raw_left = self.fuse_knee_angle(imu_left_knee, frame.flex_left_knee)
        raw_right = self.fuse_knee_angle(imu_right_knee, frame.flex_right_knee)

        # Apply smoothing filter
        features.left_knee_angle = self.filter_left_knee.update(raw_left)
        features.right_knee_angle = self.filter_right_knee.update(raw_right)

        # Angular velocity (degrees per second)
        dt = (frame.timestamp - self.prev_timestamp) / 1000.0 if self.prev_timestamp else 0.02
        dt = max(dt, 0.001)  # Prevent division by zero
        features.left_knee_angular_velocity = (features.left_knee_angle - self.prev_left_knee) / dt
        features.right_knee_angular_velocity = (features.right_knee_angle - self.prev_right_knee) / dt

        self.prev_left_knee = features.left_knee_angle
        self.prev_right_knee = features.right_knee_angle
        self.prev_timestamp = frame.timestamp

        # --- 2. GAIT ANALYSIS ---
        features.gait_phase_left = self.gait_left.update(frame.fsr_left_foot)
        features.gait_phase_right = self.gait_right.update(frame.fsr_right_foot)

        # Step detection (count heel strikes)
        now = time.time()
        if features.gait_phase_left == "heel_strike" or features.gait_phase_right == "heel_strike":
            if now - self.last_step_time > 0.3:  # Min 300ms between steps
                self.step_count += 1
                self.step_timestamps.append(now)
                self.last_step_time = now

        features.step_count = self.step_count

        # Cadence calculation (steps per minute from recent step timestamps)
        if len(self.step_timestamps) >= 2:
            time_span = self.step_timestamps[-1] - self.step_timestamps[0]
            if time_span > 0:
                features.cadence = (len(self.step_timestamps) - 1) / time_span * 60.0

        # Stride time (average time between consecutive steps)
        if len(self.step_timestamps) >= 3:
            intervals = [self.step_timestamps[i+1] - self.step_timestamps[i] 
                        for i in range(len(self.step_timestamps) - 1)]
            features.stride_time = sum(intervals) / len(intervals)

        # --- 3. LOAD DISTRIBUTION ---
        features.left_foot_load = frame.fsr_left_foot.total()
        features.right_foot_load = frame.fsr_right_foot.total()

        total_load = features.left_foot_load + features.right_foot_load
        if total_load > 0:
            features.load_asymmetry = abs(features.left_foot_load - features.right_foot_load) / total_load
        
        features.left_cop = frame.fsr_left_foot.center_of_pressure()
        features.right_cop = frame.fsr_right_foot.center_of_pressure()

        # --- 4. ACCELEROMETER MAGNITUDES ---
        features.left_thigh_accel_mag = frame.imu_left_thigh.accel.magnitude()
        features.right_thigh_accel_mag = frame.imu_right_thigh.accel.magnitude()
        features.left_shin_accel_mag = frame.imu_left_shin.accel.magnitude()
        features.right_shin_accel_mag = frame.imu_right_shin.accel.magnitude()

        # --- 5. ALERTS ---
        alerts = []
        if features.left_knee_angle > self.KNEE_ANGLE_MAX:
            alerts.append(f"Left knee hyperextension ({features.left_knee_angle:.0f}°)")
        if features.right_knee_angle > self.KNEE_ANGLE_MAX:
            alerts.append(f"Right knee hyperextension ({features.right_knee_angle:.0f}°)")
        if features.load_asymmetry > self.LOAD_ASYMMETRY_WARN:
            alerts.append(f"Load asymmetry warning ({features.load_asymmetry:.0%})")

        if alerts:
            features.alert = True
            features.alert_message = "; ".join(alerts)

        # Store in history
        self.history.append(features)

        return features

    def get_summary(self) -> dict:
        """Return a summary of accumulated metrics."""
        if not self.history:
            return {}

        recent = list(self.history)[-50:]  # Last ~1 second
        return {
            "avg_left_knee": round(sum(f.left_knee_angle for f in recent) / len(recent), 1),
            "avg_right_knee": round(sum(f.right_knee_angle for f in recent) / len(recent), 1),
            "max_left_knee": round(max(f.left_knee_angle for f in recent), 1),
            "max_right_knee": round(max(f.right_knee_angle for f in recent), 1),
            "step_count": self.step_count,
            "avg_cadence": round(sum(f.cadence for f in recent) / len(recent), 1),
            "avg_asymmetry": round(sum(f.load_asymmetry for f in recent) / len(recent), 3),
        }
