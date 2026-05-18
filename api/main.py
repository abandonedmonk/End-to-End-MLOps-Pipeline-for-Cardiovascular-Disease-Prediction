from fastapi import FastAPI
from schema import PatientData # Run after cd api
import pandas as pd
import numpy as np
import os
from dotenv import load_dotenv
import mlflow
import mlflow.pyfunc

load_dotenv()

app = FastAPI()

# Read configuration from environment
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI")
MODEL_NAME = os.getenv("MODEL_NAME", "heart-disease-model")
AWS_REGION = os.getenv("AWS_REGION")

if MLFLOW_TRACKING_URI:
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)

# Attempt to load model from MLflow registry (Production stage)
pipeline = None
model_uri = f"models:/{MODEL_NAME}/Production"
try:
    pipeline = mlflow.pyfunc.load_model(model_uri)
    print(f"Loaded model from MLflow: {model_uri}")
except Exception as e:
    print(f"Failed to load model from MLflow ({model_uri}): {e}")


@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": pipeline is not None}


@app.post("/predict")
def predict_endpoint(data: PatientData):
    if pipeline is None:
        return {"error": "Model not loaded"}

    try:
        feature_names = [
            'age', 'sex', 'cp', 'trestbps', 'chol', 'fbs',
            'restecg', 'thalach', 'exang', 'oldpeak',
            'slope', 'ca', 'thal'
        ]
        df = pd.DataFrame([data.model_dump()], columns=feature_names)

        # Normalize types similar to previous implementation
        df = df.astype({
            "age": int, "sex": int, "cp": int, "trestbps": int,
            "chol": int, "fbs": int, "restecg": int, "thalach": int,
            "exang": int, "oldpeak": float, "slope": int,
            "ca": str, "thal": str
        })
        df['thal'] = df['thal'].astype(str).apply(lambda x: f"{float(x):.1f}" if x.replace('.', '', 1).isdigit() else x)
        df['ca'] = df['ca'].astype(str).apply(lambda x: f"{float(x):.1f}" if x.replace('.', '', 1).isdigit() else x)

        prediction = pipeline.predict(df)
        prediction_value = int(prediction[0]) if isinstance(prediction, (list, np.ndarray)) else int(prediction)
        return {"prediction": prediction_value}

    except Exception as e:
        print(f"❌ Prediction failed: {e}")
        return {"error": str(e)}
