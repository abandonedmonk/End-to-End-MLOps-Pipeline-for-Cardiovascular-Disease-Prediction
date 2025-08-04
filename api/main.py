from fastapi import FastAPI
from schema import PatientData # Run after cd api
import pandas as pd
import pickle
import numpy as np
app = FastAPI()

# Load the full pipeline (preprocessor + model)
with open("../models/pipeline.pkl", "rb") as f:
    pipeline = pickle.load(f)

@app.post("/predict")
def predict_endpoint(data: PatientData):
    try:
        # Convert the input to a DataFrame
        feature_names = [
            'age', 'sex', 'cp', 'trestbps', 'chol', 'fbs',
            'restecg', 'thalach', 'exang', 'oldpeak',
            'slope', 'ca', 'thal'
        ]
        df = pd.DataFrame([data.model_dump()], columns=feature_names)
        print(f"Raw DataFrame:\n{df}")
        df = df.astype({
            "age": int, "sex": int, "cp": int, "trestbps": int,
            "chol": int, "fbs": int, "restecg": int, "thalach": int,
            "exang": int, "oldpeak": int, "slope": int,
            "ca": str, "thal": str
        })
        df['thal'] = df['thal'].astype(str).apply(lambda x: f"{float(x):.1f}" if x.replace('.', '', 1).isdigit() else x)
        df['ca'] = df['ca'].astype(str).apply(lambda x: f"{float(x):.1f}" if x.replace('.', '', 1).isdigit() else x)

        print(f"📊 Input DataFrame:\n{df}")
        prediction = pipeline.predict(df)
        print(f"Prediction: {prediction}")

        prediction_value = int(prediction[0]) if isinstance(prediction, np.ndarray) else int(prediction)
        if prediction_value == 0:
            print("No heart disease detected.")
        else:
            print("Heart disease detected.")
        return {"prediction": prediction_value}
    
    except Exception as e:
        print(f"❌ Prediction failed: {e}")
        return {"error": str(e)}
