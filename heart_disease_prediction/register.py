from prefect import task
from prefect.logging import get_run_logger
import mlflow
from mlflow.tracking import MlflowClient
from mlflow.entities import ViewType
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.compose import ColumnTransformer
from typing import Union, Dict, Tuple
from datetime import date

    

def register_model(
    # model: Union[RandomForestClassifier, HistGradientBoostingClassifier, LogisticRegression, DecisionTreeClassifier], 
    preprocessor: ColumnTransformer, 
    paths: Dict
) -> Dict:
    """Register the model and DictVectorizer with MLflow."""
    logger = get_run_logger()
    try:
        mlflow.set_tracking_uri(paths["mlflow_db_path"])
        mlflow.set_experiment(experiment_name=paths["experiment_name"])

        client = MlflowClient()

        # Evaluate based on Accuracy
        experiment = client.get_experiment_by_name(paths["experiment_name"])
        best_run = client.search_runs(
            experiment_ids=experiment.experiment_id,
            run_view_type=ViewType.ACTIVE_ONLY,
            max_results=1,
            order_by=["metrics.accuracy DESC"]
        )[0]

        mlflow.sklearn.log_model(
            preprocessor, 
            "preprocessor",
            registered_model_name="Preprocessor"
        )
        model_name = f"best_model_{date.today()}"
        result = mlflow.register_model(
            model_uri=f"runs:/{best_run.info.run_id}/model",
            name=model_name
        )
        paths["model_name"] = model_name

        logger.info(f"✅ Model registered successfully: version {result.version}")

        return paths

    except Exception as e:
        logger.error(f"❌ Model registration failed: {e}")


