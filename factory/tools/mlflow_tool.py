"""MLflow tool — experiment tracking and model registry.

Open source: https://mlflow.org  (Apache-2.0)
Self-hosted: mlflow server --host 0.0.0.0 --port 5000

Env vars:
  MLFLOW_TRACKING_URI — MLflow server URL (default: http://localhost:5000)
  MLFLOW_EXPERIMENT   — default experiment name (default: ai-factory)
"""

import logging
import os

log = logging.getLogger(__name__)

MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
MLFLOW_EXPERIMENT = os.getenv("MLFLOW_EXPERIMENT", "ai-factory")


def _client():
    """Get an MLflow tracking client."""
    try:
        import mlflow
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        return mlflow
    except ImportError:
        return None


# ── Experiments ───────────────────────────────────────────────────────────────

def create_experiment(name: str, tags: dict | None = None) -> dict:
    """Create or get an MLflow experiment.

    Returns: {"experiment_id": str, "experiment_url": str}
    """
    mlflow = _client()
    if not mlflow:
        return {"experiment_id": "", "warning": "mlflow not installed — pip install mlflow"}
    try:
        exp_id = mlflow.create_experiment(name, tags=tags or {})
        url = f"{MLFLOW_TRACKING_URI}/#/experiments/{exp_id}"
        log.info("MLflow experiment created: %s (%s)", name, exp_id)
        return {"experiment_id": exp_id, "experiment_url": url}
    except Exception as e:
        # Experiment may already exist
        try:
            exp = mlflow.get_experiment_by_name(name)
            if exp:
                url = f"{MLFLOW_TRACKING_URI}/#/experiments/{exp.experiment_id}"
                return {"experiment_id": exp.experiment_id, "experiment_url": url}
        except Exception:
            pass
        return {"experiment_id": "", "error": str(e)}


# ── Runs ──────────────────────────────────────────────────────────────────────

def log_run(
    experiment_name: str,
    run_name: str,
    params: dict | None = None,
    metrics: dict | None = None,
    tags: dict | None = None,
    artifacts: dict[str, str] | None = None,
) -> dict:
    """Log an ML run with params, metrics, and optional file artifacts.

    artifacts: {"filename.txt": "file_content_string"}
    Returns: {"run_id": str, "run_url": str, "status": str}
    """
    mlflow = _client()
    if not mlflow:
        log.warning("mlflow not installed — skipping run logging")
        return {"run_id": "", "warning": "mlflow not installed"}

    import tempfile
    from pathlib import Path

    try:
        mlflow.set_experiment(experiment_name)
        with mlflow.start_run(run_name=run_name, tags=tags or {}) as run:
            if params:
                mlflow.log_params(params)
            if metrics:
                mlflow.log_metrics(metrics)
            if artifacts:
                with tempfile.TemporaryDirectory(prefix="aifactory-mlflow-") as tmp:
                    for fname, content in artifacts.items():
                        fpath = Path(tmp) / fname
                        fpath.write_text(content, encoding="utf-8")
                        mlflow.log_artifact(str(fpath))

            run_id = run.info.run_id
            url = f"{MLFLOW_TRACKING_URI}/#/experiments/{run.info.experiment_id}/runs/{run_id}"
            log.info("MLflow run: %s / %s → %s", experiment_name, run_name, run_id)
            return {"run_id": run_id, "run_url": url, "status": "RUNNING"}
    except Exception as e:
        log.warning("MLflow log_run failed: %s", e)
        return {"run_id": "", "error": str(e)}


# ── Model Registry ────────────────────────────────────────────────────────────

def register_model(run_id: str, model_name: str, model_path: str = "model") -> dict:
    """Register a model from a run into the MLflow Model Registry.

    Returns: {"model_name": str, "version": str, "registry_url": str}
    """
    mlflow = _client()
    if not mlflow:
        return {"model_name": "", "warning": "mlflow not installed"}
    try:
        model_uri = f"runs:/{run_id}/{model_path}"
        result = mlflow.register_model(model_uri, model_name)
        url = f"{MLFLOW_TRACKING_URI}/#/models/{model_name}"
        log.info("Registered model: %s v%s", model_name, result.version)
        return {"model_name": model_name, "version": str(result.version), "registry_url": url}
    except Exception as e:
        log.warning("MLflow register_model failed: %s", e)
        return {"model_name": model_name, "error": str(e)}


def list_models() -> dict:
    """List all registered models.

    Returns: {"models": [{"name", "latest_version", "url"}]}
    """
    mlflow = _client()
    if not mlflow:
        return {"models": [], "warning": "mlflow not installed"}
    try:
        from mlflow.tracking import MlflowClient
        client = MlflowClient(tracking_uri=MLFLOW_TRACKING_URI)
        models = [
            {
                "name": m.name,
                "latest_version": m.latest_versions[0].version if m.latest_versions else "0",
                "url": f"{MLFLOW_TRACKING_URI}/#/models/{m.name}",
            }
            for m in client.search_registered_models()
        ]
        return {"models": models, "count": len(models)}
    except Exception as e:
        return {"models": [], "error": str(e)}
