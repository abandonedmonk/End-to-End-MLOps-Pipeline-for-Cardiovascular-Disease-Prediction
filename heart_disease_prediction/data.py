import os
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv
import boto3
from prefect import task
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder
from sklearn.model_selection import train_test_split

load_dotenv()

DATA_PATH = os.getenv("DATA_PATH", "../data/raw/processed.cleveland.data")
LOCAL_DATA_CACHE = Path(os.getenv("LOCAL_DATA_CACHE", "/tmp/heart_disease_prediction"))


def _resolve_data_path(path: str) -> str:
    if not path.startswith("s3://"):
        return path

    parsed = urlparse(path)
    bucket = parsed.netloc
    key = parsed.path.lstrip("/")

    LOCAL_DATA_CACHE.mkdir(parents=True, exist_ok=True)
    local_path = LOCAL_DATA_CACHE / Path(key).name
    boto3.client("s3").download_file(bucket, key, str(local_path))
    return str(local_path)

@task
def get_data(path: str = DATA_PATH) -> pd.DataFrame:
    local_path = _resolve_data_path(path)
    df = pd.read_csv(local_path, header=None)
    df.columns = [
        'age', 'sex', 'cp', 'trestbps', 'chol', 'fbs', 'restecg', 'thalach', 'exang', 'oldpeak', 'slope', 'ca', 'thal', 'hd'	
    ]
    y_not_zero = df["hd"] > 0
    df.loc[y_not_zero, "hd"] = 1
    print(f"Final Number of records after loading is {len(df)}")
    return df

# Splitting the Data
@task
def split_data_for_train(df: pd.DataFrame):
    # Independent and Dependent Variables
    X = df.drop('hd', axis=1).copy()
    y = df['hd'].copy()

    # Seperating the Cols based on their types
    numerical_cols = ['age', 'sex', 'trestbps', 'chol', 'fbs', 'thalach', 'exang', 'oldpeak']
    categorical_cols = ['restecg', 'slope', 'thal', 'ca', 'cp'] # We will pass this through OneHotEncoder

    # Making the preprocessor that will be applied on the data
    preprocessor = ColumnTransformer(
        transformers=[
            ('num', 'passthrough', numerical_cols),                  # Keep numerical columns as is
            ('cat', OneHotEncoder(drop='first'), categorical_cols)   # One-hot encode categorical columns
        ]
    )

    # We only need to detect the heart disease, not their severity
    y_not_zero = y > 0
    y[y_not_zero] = 1

    # SPLIT
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    # Fit and transform the data using the preprocessor
    # X_train_transformed = preprocessor.fit_transform(X_train)
    # X_test_transformed = preprocessor.transform(X_test)

    return X_train, X_test, y_train, y_test, preprocessor
