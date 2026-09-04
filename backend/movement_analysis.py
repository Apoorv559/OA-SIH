import cv2
import mediapipe as mp
import numpy as np
from scipy.signal import find_peaks

mp_pose = mp.solutions.pose

def calculate_angle(a, b, c):
    """
    Calculate angle between 3 points.
    a, b, c are lists or tuples of (x,y) or (x,y,z) coordinates.
    b is the vertex.
    """
    a = np.array(a)
    b = np.array(b)
    c = np.array(c)
    
    radians = np.arctan2(c[1]-b[1], c[0]-b[0]) - np.arctan2(a[1]-b[1], a[0]-b[0])
    angle = np.abs(radians * 180.0 / np.pi)
    
    if angle > 180.0:
        angle = 360 - angle
        
    return angle

def extract_gait_features(left_ankle_x, right_ankle_x, fps, left_knee_angles, right_knee_angles):
    """
    Extracts advanced gait features from a walking sequence.
    """
    # 1. Calculate ankle distance over time to find heel strikes
    # Heel strikes roughly correspond to maximum distance between ankles
    ankle_distances = np.abs(np.array(left_ankle_x) - np.array(right_ankle_x))
    
    # Smooth the signal slightly
    window_size = 5
    if len(ankle_distances) > window_size:
        kernel = np.ones(window_size) / window_size
        ankle_distances = np.convolve(ankle_distances, kernel, mode='same')
        
    # Find peaks (heel strikes)
    peaks, _ = find_peaks(ankle_distances, distance=int(fps*0.5), prominence=np.max(ankle_distances)*0.2)
    
    if len(peaks) < 2:
        return {"error": "Not enough steps detected for gait analysis"}

    # Time between consecutive peaks = step duration (in seconds)
    step_durations = np.diff(peaks) / fps
    
    # Stride duration (two steps)
    stride_durations = []
    for i in range(len(peaks) - 2):
        stride_durations.append((peaks[i+2] - peaks[i]) / fps)
        
    avg_step_duration = np.mean(step_durations) if len(step_durations) > 0 else 0
    avg_stride_duration = np.mean(stride_durations) if len(stride_durations) > 0 else (avg_step_duration * 2)
    
    # Cadence (steps per minute)
    cadence = (60.0 / avg_step_duration) if avg_step_duration > 0 else 0
    
    # Variability
    step_variability = np.std(step_durations) if len(step_durations) > 0 else 0
    
    # Knee Flexion/Extension (Max/Min angles)
    left_flexion = np.max(left_knee_angles)
    left_extension = np.min(left_knee_angles)
    right_flexion = np.max(right_knee_angles)
    right_extension = np.min(right_knee_angles)
    
    # Symmetry
    symmetry = 100 - (abs(left_flexion - right_flexion) / max(left_flexion, right_flexion)) * 100
    
    # Dummy Gait Speed based on cadence (heuristic)
    # Average step length = 0.7m. Speed = cadence * step_length / 60
    gait_speed = (cadence * 0.7) / 60.0
    
    return {
        "cadence": round(cadence, 2),
        "step_duration_sec": round(avg_step_duration, 2),
        "stride_duration_sec": round(avg_stride_duration, 2),
        "gait_speed_m_s": round(gait_speed, 2),
        "movement_variability": round(step_variability, 3),
        "left_knee_flexion_max": round(left_flexion, 2),
        "left_knee_extension_min": round(left_extension, 2),
        "right_knee_flexion_max": round(right_flexion, 2),
        "right_knee_extension_min": round(right_extension, 2),
        "gait_symmetry": round(symmetry, 2),
    }

def analyze_video(video_path: str, movement_type: str = "Squat"):
    """
    Analyzes a video file and returns biomechanical metrics.
    """
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps == 0 or np.isnan(fps):
        fps = 30.0
        
    left_knee_angles = []
    right_knee_angles = []
    left_hip_angles = []
    right_hip_angles = []
    left_ankle_angles = []
    right_ankle_angles = []
    
    # For gait analysis
    left_ankle_x_series = []
    right_ankle_x_series = []
    
    # Initialize mediapipe pose
    with mp_pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5) as pose:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            
            # Recolor image to RGB
            image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image.flags.writeable = False
            
            # Make detection
            results = pose.process(image)
            
            # Extract landmarks
            try:
                landmarks = results.pose_landmarks.landmark
                
                # Get coordinates for Left side
                l_shoulder = [landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value].x, landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value].y]
                l_hip = [landmarks[mp_pose.PoseLandmark.LEFT_HIP.value].x, landmarks[mp_pose.PoseLandmark.LEFT_HIP.value].y]
                l_knee = [landmarks[mp_pose.PoseLandmark.LEFT_KNEE.value].x, landmarks[mp_pose.PoseLandmark.LEFT_KNEE.value].y]
                l_ankle = [landmarks[mp_pose.PoseLandmark.LEFT_ANKLE.value].x, landmarks[mp_pose.PoseLandmark.LEFT_ANKLE.value].y]
                l_foot = [landmarks[mp_pose.PoseLandmark.LEFT_FOOT_INDEX.value].x, landmarks[mp_pose.PoseLandmark.LEFT_FOOT_INDEX.value].y]
                
                # Get coordinates for Right side
                r_shoulder = [landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value].x, landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value].y]
                r_hip = [landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value].x, landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value].y]
                r_knee = [landmarks[mp_pose.PoseLandmark.RIGHT_KNEE.value].x, landmarks[mp_pose.PoseLandmark.RIGHT_KNEE.value].y]
                r_ankle = [landmarks[mp_pose.PoseLandmark.RIGHT_ANKLE.value].x, landmarks[mp_pose.PoseLandmark.RIGHT_ANKLE.value].y]
                r_foot = [landmarks[mp_pose.PoseLandmark.RIGHT_FOOT_INDEX.value].x, landmarks[mp_pose.PoseLandmark.RIGHT_FOOT_INDEX.value].y]
                
                # Calculate angles
                left_knee_angles.append(calculate_angle(l_hip, l_knee, l_ankle))
                right_knee_angles.append(calculate_angle(r_hip, r_knee, r_ankle))
                
                left_hip_angles.append(calculate_angle(l_shoulder, l_hip, l_knee))
                right_hip_angles.append(calculate_angle(r_shoulder, r_hip, r_knee))
                
                left_ankle_angles.append(calculate_angle(l_knee, l_ankle, l_foot))
                right_ankle_angles.append(calculate_angle(r_knee, r_ankle, r_foot))
                
                # Store coordinates for gait
                left_ankle_x_series.append(l_ankle[0])
                right_ankle_x_series.append(r_ankle[0])
                
            except Exception as e:
                pass
                
    cap.release()
    
    if not left_knee_angles:
        return {"error": "Could not detect pose in the video"}
        
    # Calculate base statistics
    metrics = {
        "left_knee_ROM": round(max(left_knee_angles) - min(left_knee_angles), 2),
        "right_knee_ROM": round(max(right_knee_angles) - min(right_knee_angles), 2),
        "avg_left_hip_angle": round(np.mean(left_hip_angles), 2),
        "avg_right_hip_angle": round(np.mean(right_hip_angles), 2),
        "avg_left_knee_angle": round(np.mean(left_knee_angles), 2),
        "avg_right_knee_angle": round(np.mean(right_knee_angles), 2),
        "avg_left_ankle_angle": round(np.mean(left_ankle_angles), 2),
        "avg_right_ankle_angle": round(np.mean(right_ankle_angles), 2),
    }
    
    # Movement symmetry based on Knee ROM
    symmetry = 100 - abs(metrics["left_knee_ROM"] - metrics["right_knee_ROM"]) / max(metrics["left_knee_ROM"], metrics["right_knee_ROM"], 1) * 100
    metrics["movement_symmetry"] = round(symmetry, 2)
    
    # Heuristic Biomechanical Score (0-100)
    avg_rom = (metrics["left_knee_ROM"] + metrics["right_knee_ROM"]) / 2
    rom_score = min(100, (avg_rom / 110) * 100) 
    
    biomechanical_score = (rom_score * 0.6) + (metrics["movement_symmetry"] * 0.4)
    metrics["biomechanical_score"] = round(biomechanical_score, 2)
    
    # Apply Gait Feature Extraction if Walking
    if movement_type.lower() == "walking":
        gait_features = extract_gait_features(left_ankle_x_series, right_ankle_x_series, fps, left_knee_angles, right_knee_angles)
        
        if "error" not in gait_features:
            metrics["gait_vector"] = gait_features
            metrics["gait_characteristics"] = f"Cadence: {gait_features['cadence']} spm | Speed: {gait_features['gait_speed_m_s']} m/s"
            # Update symmetry using gait symmetry if available
            metrics["movement_symmetry"] = gait_features["gait_symmetry"]
        else:
            metrics["gait_characteristics"] = "Walking detected, but not enough steps for gait vector"
            metrics["gait_vector"] = None
    else:
        metrics["gait_characteristics"] = "N/A"
        metrics["gait_vector"] = None
        
    return metrics
