from fastapi import FastAPI
from api.schema import PatientData
import pandas as pd
import pickle
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder

app = FastAPI()

with open("../models/pipeline_bundle.pkl", "rb") as f:
    bundle = pickle.load(f)
    model = bundle["model"]
    preprocessor = bundle["preprocessor"]

def prepare_data(data):
    df = pd.read_json(data)
    df.columns = [
        'age', 'sex', 'cp', 'trestbps', 'chol', 'fbs', 'restecg', 'thalach', 'exang', 'oldpeak', 'slope', 'ca', 'thal', 'hd'	
    ]
    return df

def predict(data: pd.DataFrame):
    X = preprocessor.transform(data)
    y_pred = model.predict(X)
    return y_pred

# @app.post("/predict")
# def predict_endpoint(data: PatientData):
#     try:
#         feature_names = [
#             'age', 'sex', 'cp', 'trestbps', 'chol', 'fbs',
#             'restecg', 'thalach', 'exang', 'oldpeak',
#             'slope', 'ca', 'thal'
#         ]
#         df = pd.DataFrame([data.model_dump()], columns=feature_names)

#         # Convert types
#         df = df.astype({
#             "age": float, "sex": float, "cp": float, "trestbps": float,
#             "chol": float, "fbs": float, "restecg": float, "thalach": float,
#             "exang": float, "oldpeak": float, "slope": float,
#             "ca": str, "thal": str
#         })
#         # Check for missing values
#         print(df)
#         X = preprocessor.transform(df)
#         print("LMAO4")
#         prediction = model.predict(X)
#         return {"prediction": int(prediction[0])}
#     except Exception as e:
#         print(f"❌ Prediction failed: {e}")
#         return {"error": str(e)}


@app.post("/predict")
def predict_endpoint(data: PatientData):
    try:
        feature_names = [
            'age', 'sex', 'cp', 'trestbps', 'chol', 'fbs',
            'restecg', 'thalach', 'exang', 'oldpeak',
            'slope', 'ca', 'thal'
        ]
        df = pd.DataFrame([data.model_dump()], columns=feature_names)
        # Seperating the Cols based on their types
        numerical_cols = ['age', 'sex', 'trestbps', 'chol', 'fbs', 'thalach', 'exang', 'oldpeak']
        categorical_cols = ['restecg', 'slope', 'thal', 'ca', 'cp'] # We will pass this through OneHotEncoder

        # Making the preprocessor that will be applied on the data
        preprocessor = ColumnTransformer(
            transformers=[
                ('num', 'passthrough', numerical_cols),                  # Keep numerical columns as is
                ('cat', OneHotEncoder(), categorical_cols)   # One-hot encode categorical columns
            ]
        )

        X = preprocessor.fit_transform(df)
        print("LMAO4")
        prediction = model.predict(X)
        return {"prediction": int(prediction[0])}
    
    except Exception as e:
        print(f"❌ Prediction failed: {e}")
        return {"error": str(e)}
