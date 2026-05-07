"""
Log Clustering Pipeline — Kubeflow Pipeline Definition

Définit le pipeline KFP complet qui chaîne :
  1. train_model  → entraîne TF-IDF + K-Means, logue dans MLflow, retourne run_id
  2. register_model → enregistre le modèle dans le Registry, retourne model_version

Compilation :
    python pipeline.py
    → Génère log_clustering_pipeline.yaml prêt à être soumis à Kubeflow Pipelines.

Ce fichier est conçu pour être compilé et exécuté par Kubeflow Pipelines.
"""

from kfp import dsl, compiler

# Import des composants depuis les fichiers locaux
from train_model import train_model
from register_model import register_model


@dsl.pipeline(
    name="log-clustering-pipeline",
    description=(
        "Pipeline de clustering de logs Loki avec TF-IDF + K-Means. "
        "Entraîne le modèle, logue dans MLflow, et enregistre dans le Model Registry."
    ),
)
def log_clustering_pipeline(
    # MLflow configuration
    mlflow_tracking_uri: str = "http://mlflow-service:5000",
    minio_endpoint: str = "http://minio-service:9000",
    aws_access_key: str = "minioadmin",
    aws_secret_key: str = "minioadmin",
    experiment_name: str = "log-clustering-loki",
    # Data configuration
    data_path: str = "/data/mock_loki_logs.csv",
    # TF-IDF hyperparameters
    max_features: int = 100,
    min_df: int = 2,
    max_df: float = 0.95,
    # K-Means hyperparameters
    n_clusters: int = 5,
    n_init: int = 10,
    random_state: int = 42,
    # Evaluation
    k_range: str = "3,5,8,10,12,15",
    # Model Registry
    model_name: str = "log-clustering-kmeans",
):
    """
    Pipeline complet de clustering de logs Loki.

    Étapes :
        1. train_model  : charge les données, TF-IDF, K-Means, log MLflow
        2. register_model : enregistre le modèle dans le MLflow Model Registry
    """

    # ── Step 1 : Entraînement ────────────────────────────────────────
    train_task = train_model(
        mlflow_tracking_uri=mlflow_tracking_uri,
        minio_endpoint=minio_endpoint,
        aws_access_key=aws_access_key,
        aws_secret_key=aws_secret_key,
        experiment_name=experiment_name,
        data_path=data_path,
        max_features=max_features,
        min_df=min_df,
        max_df=max_df,
        n_clusters=n_clusters,
        n_init=n_init,
        random_state=random_state,
        k_range=k_range,
        model_name=model_name,
    )

    # ── Step 2 : Enregistrement dans le Model Registry ───────────────
    # register_model reçoit le run_id retourné par train_model
    register_task = register_model(
        mlflow_tracking_uri=mlflow_tracking_uri,
        minio_endpoint=minio_endpoint,
        aws_access_key=aws_access_key,
        aws_secret_key=aws_secret_key,
        run_id=train_task.output,
        model_name=model_name,
    )


# ── Compilation du pipeline en YAML ──────────────────────────────────
if __name__ == "__main__":
    output_file = "log_clustering_pipeline.yaml"
    compiler.Compiler().compile(
        pipeline_func=log_clustering_pipeline,
        package_path=output_file,
    )
    print(f"✅ Pipeline compilé : {output_file}")
    print("   Soumettez ce fichier à Kubeflow Pipelines pour exécution.")
