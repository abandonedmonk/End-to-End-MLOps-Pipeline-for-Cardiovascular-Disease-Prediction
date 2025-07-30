from prefect import flow, task
from heart_disease_prediction.data import get_data, split_data_for_train
from heart_disease_prediction.register import register_model
from heart_disease_prediction.train import train_model
from heart_disease_prediction.load_model import load_model

@flow
def full_pipeline():
    df = get_data(path="./data/raw/processed.cleveland.data")
    X_train, X_test, y_train, y_test, preprocessor = split_data_for_train(df)
    _, pipeline, paths = train_model(X_train, X_test, y_train, y_test, preprocessor)
    paths = register_model(pipeline, paths)
    load_model(paths)

if __name__ == "__main__":
    full_pipeline()

