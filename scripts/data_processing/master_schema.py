"""
master_schema.py
================
Defines the canonical Master Feature Schema for the Osteoarthritis Prediction project.

Every raw dataset (OAI, MOST, KNOAP2020) must be mapped into this schema before
any downstream modelling. New data sources should add their column mappings here.

Schema columns are grouped into 6 logical blocks:
  1. Demographics & Anthropometrics
  2. Medical History
  3. Clinical Examination (symptoms, physical exam)
  4. Lifestyle & Occupation
  5. Gait Parameters (from ESP32/sensor / dataset-derived)
  6. Outcome Labels
"""

# ---------------------------------------------------------------------------
# 1. MASTER SCHEMA DEFINITION
# ---------------------------------------------------------------------------

MASTER_SCHEMA = {
    # ── Demographics & Anthropometrics ──────────────────────────────────────
    "patient_id": {
        "dtype": "str",
        "description": "Unique patient identifier across all datasets",
        "source_datasets": ["OAI", "MOST", "KNOAP2020", "ESP32"],
        "nullable": False,
    },
    "age": {
        "dtype": "float32",
        "unit": "years",
        "description": "Age of the patient at enrollment / visit",
        "range": [18, 100],
        "nullable": False,
    },
    "sex": {
        "dtype": "int8",
        "description": "Biological sex  (0 = Female, 1 = Male)",
        "values": {0: "Female", 1: "Male"},
        "nullable": False,
    },
    "height": {
        "dtype": "float32",
        "unit": "cm",
        "description": "Standing height",
        "range": [100, 220],
        "nullable": True,
    },
    "weight": {
        "dtype": "float32",
        "unit": "kg",
        "description": "Body weight",
        "range": [30, 250],
        "nullable": True,
    },
    "bmi": {
        "dtype": "float32",
        "unit": "kg/m²",
        "description": "Body Mass Index = weight / height²",
        "range": [10, 70],
        "nullable": True,
        "derived": True,
    },
    "waist": {
        "dtype": "float32",
        "unit": "cm",
        "description": "Waist / abdominal circumference",
        "range": [40, 200],
        "nullable": True,
    },

    # ── Medical History ──────────────────────────────────────────────────────
    "previous_injury": {
        "dtype": "int8",
        "description": "History of knee injury  (0 = No, 1 = Yes)",
        "values": {0: "No", 1: "Yes"},
        "nullable": True,
    },
    "injury_type": {
        "dtype": "str",
        "description": "Type of previous knee injury (e.g. 'meniscal', 'ligament', 'fracture', 'other')",
        "nullable": True,
    },
    "surgery": {
        "dtype": "int8",
        "description": "History of knee surgery  (0 = No, 1 = Yes)",
        "values": {0: "No", 1: "Yes"},
        "nullable": True,
    },
    "diabetes": {
        "dtype": "int8",
        "description": "Diabetes diagnosis  (0 = No, 1 = Yes)",
        "values": {0: "No", 1: "Yes"},
        "nullable": True,
    },
    "hypertension": {
        "dtype": "int8",
        "description": "Hypertension diagnosis OR SBP ≥ 140 / DBP ≥ 90 mmHg  (0 = No, 1 = Yes)",
        "values": {0: "No", 1: "Yes"},
        "nullable": True,
    },

    # ── Lifestyle & Occupation ───────────────────────────────────────────────
    "occupation": {
        "dtype": "str",
        "description": "Occupational category (e.g. 'sedentary', 'light', 'moderate', 'heavy')",
        "nullable": True,
    },
    "physical_activity": {
        "dtype": "float32",
        "unit": "MET-min/week",
        "description": "Weekly physical activity level in MET-minutes",
        "range": [0, 10000],
        "nullable": True,
    },
    "sedentary_time": {
        "dtype": "float32",
        "unit": "hours/day",
        "description": "Average daily sedentary (light-activity) time",
        "range": [0, 24],
        "nullable": True,
    },

    # ── Clinical Examination ─────────────────────────────────────────────────
    "pain_score": {
        "dtype": "float32",
        "description": "Overall knee pain score (WOMAC pain subscale 0–100, higher = more pain)",
        "range": [0, 100],
        "nullable": True,
    },
    "morning_stiffness": {
        "dtype": "float32",
        "description": "Morning stiffness score (WOMAC stiffness subscale 0–100, higher = stiffer)",
        "range": [0, 100],
        "nullable": True,
    },
    "swelling": {
        "dtype": "int8",
        "description": "Knee joint effusion / swelling on exam  (0 = No, 1 = Yes)",
        "values": {0: "No", 1: "Yes"},
        "nullable": True,
    },
    "crepitus": {
        "dtype": "int8",
        "description": "Crepitus on examination  (0 = Absent, 1 = Present)",
        "values": {0: "Absent", 1: "Present"},
        "nullable": True,
    },
    "rom": {
        "dtype": "float32",
        "unit": "degrees",
        "description": "Knee range of motion (flexion–extension arc)",
        "range": [0, 180],
        "nullable": True,
    },
    "muscle_strength": {
        "dtype": "float32",
        "unit": "Nm or kg-f",
        "description": "Quadriceps / knee extensor strength",
        "range": [0, 500],
        "nullable": True,
    },

    # ── Gait Parameters (sensor / performance-derived) ───────────────────────
    "gait_speed": {
        "dtype": "float32",
        "unit": "m/s",
        "description": "Comfortable walking speed",
        "range": [0, 3.0],
        "nullable": True,
    },
    "cadence": {
        "dtype": "float32",
        "unit": "steps/min",
        "description": "Number of steps per minute",
        "range": [0, 200],
        "nullable": True,
    },
    "stride_time": {
        "dtype": "float32",
        "unit": "seconds",
        "description": "Time for one full gait cycle (heel-strike to heel-strike, same foot)",
        "range": [0, 5.0],
        "nullable": True,
    },
    "stance_time": {
        "dtype": "float32",
        "unit": "seconds",
        "description": "Duration of stance phase per stride",
        "range": [0, 3.0],
        "nullable": True,
    },
    "swing_time": {
        "dtype": "float32",
        "unit": "seconds",
        "description": "Duration of swing phase per stride",
        "range": [0, 2.0],
        "nullable": True,
    },
    "gait_symmetry": {
        "dtype": "float32",
        "unit": "ratio",
        "description": "Symmetry index between left and right stride (1.0 = perfectly symmetric)",
        "range": [0, 2.0],
        "nullable": True,
    },

    # ── Outcome Labels ───────────────────────────────────────────────────────
    "oa_status": {
        "dtype": "int8",
        "description": "Knee OA diagnosis status at current visit  (0 = No OA, 1 = OA present)",
        "values": {0: "No OA", 1: "OA Present"},
        "nullable": False,
    },
    "progression_status": {
        "dtype": "int8",
        "description": (
            "Longitudinal OA progression label  "
            "(0 = Stable / non-progressor, 1 = Progressor at 2–4 yr follow-up)"
        ),
        "values": {0: "Stable", 1: "Progressor"},
        "nullable": True,
    },
}

# Ordered list of all canonical column names (preserves insertion order)
SCHEMA_COLUMNS = list(MASTER_SCHEMA.keys())

# Feature groups for downstream use
FEATURE_GROUPS = {
    "demographics": [
        "patient_id", "age", "sex", "height", "weight", "bmi", "waist"
    ],
    "medical_history": [
        "previous_injury", "injury_type", "surgery", "diabetes", "hypertension"
    ],
    "lifestyle": [
        "occupation", "physical_activity", "sedentary_time"
    ],
    "clinical": [
        "pain_score", "morning_stiffness", "swelling", "crepitus", "rom", "muscle_strength"
    ],
    "gait": [
        "gait_speed", "cadence", "stride_time", "stance_time", "swing_time", "gait_symmetry"
    ],
    "labels": [
        "oa_status", "progression_status"
    ],
}

# Columns that MUST be present (non-nullable core identifiers + labels)
REQUIRED_COLUMNS = [
    col for col, meta in MASTER_SCHEMA.items() if not meta.get("nullable", True)
]

if __name__ == "__main__":
    print("=== Master Feature Schema ===\n")
    for group, cols in FEATURE_GROUPS.items():
        print(f"[{group.upper()}]")
        for col in cols:
            meta = MASTER_SCHEMA[col]
            unit = f" ({meta.get('unit', '')})" if meta.get("unit") else ""
            print(f"  {col:<22} {meta['dtype']:<10} {unit} — {meta['description'][:60]}")
        print()
    print(f"Total features : {len(SCHEMA_COLUMNS)}")
    print(f"Required fields: {REQUIRED_COLUMNS}")
