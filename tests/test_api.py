from fastapi.testclient import TestClient
import mlflow.pyfunc


def _client_with_model(monkeypatch, import_fresh, model):
    monkeypatch.setattr(mlflow.pyfunc, "load_model", lambda uri: model)
    module = import_fresh("api.main")
    return TestClient(module.app)


def test_health_endpoint_reports_loaded_model(monkeypatch, import_fresh, dummy_model):
    """Validate /health returns ok and model_loaded=true when MLflow load succeeds."""
    client = _client_with_model(monkeypatch, import_fresh, dummy_model)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["model_loaded"] is True


def test_health_endpoint_reports_unloaded_model(monkeypatch, import_fresh):
    """Validate /health stays available when MLflow load fails."""

    def fail_load(*args, **kwargs):
        raise RuntimeError("no registry")

    monkeypatch.setattr(mlflow.pyfunc, "load_model", fail_load)
    module = import_fresh("api.main")
    client = TestClient(module.app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["model_loaded"] is False


def test_predict_endpoint_returns_prediction_and_probability(
    monkeypatch, import_fresh, dummy_model, patient_payload
):
    """Validate /predict returns a binary prediction and probability for valid input."""
    client = _client_with_model(monkeypatch, import_fresh, dummy_model)

    response = client.post("/predict", json=patient_payload)

    assert response.status_code == 200
    assert response.json()["prediction"] in {0, 1}
    assert 0 <= response.json()["probability"] <= 1


def test_predict_endpoint_rejects_missing_fields(
    monkeypatch, import_fresh, dummy_model, patient_payload
):
    """Validate /predict returns 422 when required fields are missing."""
    client = _client_with_model(monkeypatch, import_fresh, dummy_model)
    patient_payload.pop("age")

    response = client.post("/predict", json=patient_payload)

    assert response.status_code == 422


def test_predict_endpoint_rejects_wrong_types(
    monkeypatch, import_fresh, dummy_model, patient_payload
):
    """Validate Pydantic rejects nonnumeric values for numeric patient fields."""
    client = _client_with_model(monkeypatch, import_fresh, dummy_model)
    patient_payload["age"] = "not-a-number"

    response = client.post("/predict", json=patient_payload)

    assert response.status_code == 422
