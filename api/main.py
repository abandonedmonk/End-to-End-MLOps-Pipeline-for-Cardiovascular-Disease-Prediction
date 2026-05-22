import os
from datetime import date
from typing import Any

import boto3
import mlflow
import mlflow.pyfunc
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI

try:
    from api.schema import PatientData
except ImportError:
    from schema import PatientData

load_dotenv()

app = FastAPI()

MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI")
MODEL_NAME = os.getenv("MODEL_NAME", f"best_model_{date.today().isoformat()}")
AWS_REGION = os.getenv("AWS_REGION")

if MLFLOW_TRACKING_URI:
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)

if AWS_REGION:
    boto3.setup_default_session(region_name=AWS_REGION)

def _load_pipeline() -> tuple[Any | None, str | None]:
    model_uris = [
        f"models:/{MODEL_NAME}@champion",
        f"models:/{MODEL_NAME}/Production",
    ]

    last_error: Exception | None = None
    for model_uri in model_uris:
        try:
            return mlflow.pyfunc.load_model(model_uri), model_uri
        except Exception as exc:
            last_error = exc

    print(f"Failed to load model from MLflow ({model_uris}): {last_error}")
    return None, None


pipeline, loaded_model_uri = _load_pipeline()

if loaded_model_uri:
    print(f"Loaded model from MLflow: {loaded_model_uri}")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model_loaded": pipeline is not None,
        "model_name": MODEL_NAME,
        "tracking_uri_set": bool(MLFLOW_TRACKING_URI),
    }


@app.post("/predict")
def predict_endpoint(data: PatientData):
    if pipeline is None:
        return {"error": "Model not loaded from MLflow"}

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
        response = {"prediction": prediction_value}

        if hasattr(pipeline, "predict_proba"):
            probabilities = pipeline.predict_proba(df)
            response["probability"] = float(probabilities[0][prediction_value])

        return response

    except Exception as e:
        print(f"❌ Prediction failed: {e}")
        return {"error": str(e)}
