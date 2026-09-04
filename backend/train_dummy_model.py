import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
import joblib
import os

def create_and_train_model():
    # Define features
    numeric_features = ['Age', 'Height', 'Weight', 'BMI', 'Pain']
    categorical_features = ['Sex', 'Previous_injury', 'Surgery', 'Family_history', 
                            'Occupation', 'Physical_activity', 'Morning_stiffness', 
                            'Functional_limitations', 'Relevant_comorbidities']

    # Preprocessing pipelines
    numeric_transformer = Pipeline(steps=[
        ('scaler', StandardScaler())
    ])

    categorical_transformer = Pipeline(steps=[
        ('onehot', OneHotEncoder(handle_unknown='ignore'))
    ])

    preprocessor = ColumnTransformer(
        transformers=[
            ('num', numeric_transformer, numeric_features),
            ('cat', categorical_transformer, categorical_features)
        ])

    # Append classifier to preprocessing pipeline
    # The target will be a generic 3-class target: 0 (Low), 1 (Moderate), 2 (High) OA Risk
    clf = Pipeline(steps=[('preprocessor', preprocessor),
                          ('classifier', RandomForestClassifier(n_estimators=50, random_state=42))])

    # Generate some dummy data
    np.random.seed(42)
    n_samples = 200
    
    # Generate random numeric data
    age = np.random.randint(20, 90, n_samples)
    height = np.random.randint(150, 200, n_samples)
    weight = np.random.randint(50, 120, n_samples)
    bmi = weight / ((height/100)**2)
    pain = np.random.randint(1, 11, n_samples)
    
    # Generate random categorical data
    sex = np.random.choice(['Male', 'Female', 'Other'], n_samples)
    yes_no = ['Yes', 'No']
    prev_injury = np.random.choice(yes_no, n_samples)
    surgery = np.random.choice(yes_no, n_samples)
    family_hist = np.random.choice(yes_no, n_samples)
    occupation = np.random.choice(['Desk Job', 'Manual Labor', 'Mixed', 'Retired'], n_samples)
    activity = np.random.choice(['Low', 'Moderate', 'High'], n_samples)
    morning_stiff = np.random.choice(yes_no, n_samples)
    func_limit = np.random.choice(['None', 'Mild', 'Moderate', 'Severe'], n_samples)
    comorbidities = np.random.choice(['None', 'Diabetes', 'Hypertension', 'Obesity'], n_samples)
    
    # Generate target based loosely on some factors to make it a bit realistic
    risk_score = []
    for i in range(n_samples):
        score = 0
        if age[i] > 50: score += 1
        if bmi[i] > 30: score += 1
        if prev_injury[i] == 'Yes': score += 1
        if pain[i] > 5: score += 1
        
        if score <= 1:
            risk_score.append('Low Risk')
        elif score <= 2:
            risk_score.append('Moderate Risk')
        else:
            risk_score.append('High Risk')

    # Create DataFrame
    X = pd.DataFrame({
        'Age': age,
        'Sex': sex,
        'Height': height,
        'Weight': weight,
        'BMI': bmi,
        'Previous_injury': prev_injury,
        'Surgery': surgery,
        'Family_history': family_hist,
        'Occupation': occupation,
        'Physical_activity': activity,
        'Pain': pain,
        'Morning_stiffness': morning_stiff,
        'Functional_limitations': func_limit,
        'Relevant_comorbidities': comorbidities
    })
    
    y = np.array(risk_score)

    # Train model
    print("Training dummy model on synthetic data...")
    clf.fit(X, y)
    
    # Save model
    os.makedirs(os.path.dirname(os.path.abspath(__file__)), exist_ok=True)
    model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'model.pkl')
    joblib.dump(clf, model_path)
    print(f"Model saved to {model_path}")

if __name__ == '__main__':
    create_and_train_model()
