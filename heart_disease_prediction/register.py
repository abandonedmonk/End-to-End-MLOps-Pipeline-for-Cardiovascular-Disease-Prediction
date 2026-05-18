from prefect import task
from prefect.logging import get_run_logger
import mlflow
from mlflow.tracking import MlflowClient
from mlflow.entities import ViewType
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.pipeline import Pipeline
from typing import Union, Dict, Tuple
from datetime import date
import os
from dotenv import load_dotenv

load_dotenv()

MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "sqlite:///mlruns/mlflow.db")
EXPERIMENT_NAME = os.getenv("MLFLOW_EXPERIMENT_NAME", "heart-disease-experiment-pipeline")
MODEL_NAME = os.getenv("MODEL_NAME", f"best_model_{date.today().isoformat()}")

@task
def register_model(
    # model: Union[RandomForestClassifier, HistGradientBoostingClassifier, LogisticRegression, DecisionTreeClassifier], 
    preprocessor: Pipeline, 
    paths: Dict | None = None
) -> Dict:
    """Register the model and DictVectorizer with MLflow."""
    logger = get_run_logger()
    paths = paths or {}
    try:
        tracking_uri = paths.get("mlflow_tracking_uri", MLFLOW_TRACKING_URI)
        experiment_name = paths.get("experiment_name", EXPERIMENT_NAME)
        model_name = paths.get("model_name", MODEL_NAME)

        mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment(experiment_name=experiment_name)

        client = MlflowClient()

        # Evaluate based on Accuracy
        experiment = client.get_experiment_by_name(experiment_name)
        best_run = client.search_runs(
            experiment_ids=experiment.experiment_id,
            run_view_type=ViewType.ACTIVE_ONLY,
            max_results=1,
            order_by=["metrics.accuracy DESC"]
        )[0]

        # mlflow.sklearn.log_model(
        #     preprocessor, 
        #     "preprocessor",
        #     registered_model_name="Preprocessor"
        # )
        result = mlflow.register_model(
            model_uri=f"runs:/{best_run.info.run_id}/model",
            name=model_name
        )
        paths["model_name"] = model_name
        paths["mlflow_tracking_uri"] = tracking_uri
        paths["experiment_name"] = experiment_name

        logger.info(f"✅ Model registered successfully: version {result.version}")

        return paths

    except Exception as e:
        logger.error(f"❌ Model registration failed: {e}")


