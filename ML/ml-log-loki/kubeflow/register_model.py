"""
Log Clustering Pipeline — Kubeflow Model Registration Component

Composant KFP qui enregistre un modèle entraîné dans le MLflow Model Registry.
Reçoit le run_id du composant train_model et retourne la version du modèle.

Ce fichier est conçu pour être compilé et exécuté par Kubeflow Pipelines.
"""

from kfp import dsl


@dsl.component(
    packages_to_install=["mlflow", "boto3"]
)
def register_model(
    # MLflow configuration
    mlflow_tracking_uri: str,
    minio_endpoint: str,
    aws_access_key: str,
    aws_secret_key: str,
    # Model registration
    run_id: str,
    model_name: str,
) -> str:
    """
    Register a trained model in the MLflow Model Registry.

    Takes the run_id from the training component, locates the logged
    PyFunc model artifact, and registers it in the MLflow Model Registry.

    Args:
        mlflow_tracking_uri: MLflow tracking server URL
        minio_endpoint: MinIO S3 endpoint for artifact storage
        aws_access_key: MinIO access key
        aws_secret_key: MinIO secret key
        run_id: MLflow run ID from training component
        model_name: Name of the model in the MLflow Model Registry

    Returns:
        model_version: Version number of the registered model (as string)
    """
    # ── Imports (self-contained for KFP container isolation) ──────────
    import mlflow
    import os

    print("=" * 70)
    print("  [Register] Model Registration Component")
    print("=" * 70)

    # ── 1. Configure MLflow and MinIO environment variables ──────────
    mlflow.set_tracking_uri(mlflow_tracking_uri)

    os.environ["MLFLOW_S3_ENDPOINT_URL"] = minio_endpoint
    os.environ["AWS_ACCESS_KEY_ID"] = aws_access_key
    os.environ["AWS_SECRET_ACCESS_KEY"] = aws_secret_key

    print(f"MLflow tracking URI: {mlflow_tracking_uri}")
    print(f"MinIO endpoint configured: {minio_endpoint}")

    # ── 2. Construct model URI ───────────────────────────────────────
    # The PyFunc model was logged under artifact_path="loki_pipeline_model"
    # in the train_model component
    model_uri = f"runs:/{run_id}/loki_pipeline_model"
    print(f"Model URI: {model_uri}")

    # ── 3. Register the model ────────────────────────────────────────
    print(f"Registering model as: {model_name}")
    result = mlflow.register_model(model_uri, model_name)

    print(f"\n[SUCCESS] Model registered successfully!")
    print(f"   Name    : {model_name}")
    print(f"   Version : {result.version}")
    print(f"   Run ID  : {run_id}")
    print("=" * 70)

    # ── 4. Return model version ──────────────────────────────────────
    return str(result.version)
