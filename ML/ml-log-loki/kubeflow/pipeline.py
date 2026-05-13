"""
Log Clustering Pipeline — Kubeflow Pipeline Definition

Définit le pipeline KFP complet qui chaîne :
  1. train_model     → entraîne TF-IDF + K-Means, logue dans MLflow, retourne run_id
  2. register_model  → enregistre le modèle dans le Registry, retourne model_version
  3. validate_model  → lit les métriques MLflow (anomaly_rate), quality gate
  4. deploy_model    → Dockerfile sur PVC + patch image du Deployment serving

Compilation :
    python pipeline.py
    → Génère log_clustering_pipeline.yaml prêt à être soumis à Kubeflow Pipelines.

Ce fichier est conçu pour être compilé et exécuté par Kubeflow Pipelines.
"""

from kfp import dsl, compiler
from kfp import kubernetes

# Import des composants depuis les fichiers locaux
from train_model import train_model
from register_model import register_model
from validate_model import validate_model
from deploy_model import deploy_model


@dsl.pipeline(
    name="log-clustering-pipeline",
    description=(
        "Pipeline de clustering de logs Loki (TF-IDF + K-Means). "
        "Train → Registry → validation MLflow → patch déploiement serving."
    ),
)
def log_clustering_pipeline(
    # MLflow configuration
    mlflow_tracking_uri: str = "http://mlflow-service.default.svc.cluster.local:5000",
    minio_endpoint: str = "http://minio-service.default.svc.cluster.local:9000",
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
    # Validation (anomaly_rate = part des logs en clusters « Erreurs », seuils en %)
    anomaly_rate_min: float = 0.0,
    anomaly_rate_max: float = 100.0,
    # Déploiement Kubernetes (image déjà poussée dans le registry ; le pipeline patch le tag)
    deployment_name: str = "log-clustering-serving",
    deployment_namespace: str = "default",
    serving_container_name: str = "serving",
    serving_base_image: str = "loki-kmeans-serve",
    serving_image_tag: str = "latest",
    # PVC où écrire les Dockerfiles de référence (même PVC que les données si besoin)
    deploy_artifacts_pvc_name: str = "training-data-pvc",
):
    """
    Pipeline complet de clustering de logs Loki.

    Étapes :
        1. train_model      : données, TF-IDF, K-Means, métriques MLflow (dont anomaly_rate)
        2. register_model   : Model Registry MLflow
        3. validate_model   : API MLflow runs/get, seuils sur anomaly_rate (%)
        4. deploy_model     : artefact Dockerfile sur PVC + rolling update (image)
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

    # Mount PVC to the training task
    kubernetes.mount_pvc(
        train_task,
        pvc_name="training-data-pvc",
        mount_path="/data",
    )
    kubernetes.add_env(train_task, "AWS_ENDPOINT_URL", minio_endpoint)

    # ── Step 2 : Enregistrement dans le Model Registry ───────────────
    # register_model reçoit le run_id retourné par train_model
    register_task = register_model(
        mlflow_tracking_uri=mlflow_tracking_uri,
        minio_endpoint=minio_endpoint,
        aws_access_key=aws_access_key,
        aws_secret_key=aws_secret_key,
        run_id=train_task.outputs['Output'],
        model_name=model_name,
    )
    kubernetes.add_env(register_task, "AWS_ENDPOINT_URL", minio_endpoint)

    validate_task = validate_model(
        mlflow_tracking_uri=mlflow_tracking_uri,
        run_id=train_task.outputs['Output'],
        anomaly_rate_min=anomaly_rate_min,
        anomaly_rate_max=anomaly_rate_max,
    )
    kubernetes.add_env(validate_task, "AWS_ENDPOINT_URL", minio_endpoint)
    validate_task.after(register_task)

    deploy_task = deploy_model(
        mlflow_tracking_uri=mlflow_tracking_uri,
        minio_endpoint=minio_endpoint,
        aws_access_key=aws_access_key,
        aws_secret_key=aws_secret_key,
        model_name=model_name,
        model_version=register_task.outputs['Output'],
        deployment_name=deployment_name,
        deployment_namespace=deployment_namespace,
        container_name=serving_container_name,
        base_image=serving_base_image,
        image_tag=serving_image_tag,
    )
    kubernetes.add_env(deploy_task, "AWS_ENDPOINT_URL", minio_endpoint)
    deploy_task.after(validate_task)

    kubernetes.mount_pvc(
        deploy_task,
        pvc_name=deploy_artifacts_pvc_name,
        mount_path="/artifacts",
    )


# ── Compilation du pipeline en YAML ──────────────────────────────────
if __name__ == "__main__":
    output_file = "log_clustering_pipeline.yaml"
    compiler.Compiler().compile(
        pipeline_func=log_clustering_pipeline,
        package_path=output_file,
    )
    print(f"[SUCCESS] Pipeline compilé : {output_file}")
    print("   Soumettez ce fichier à Kubeflow Pipelines pour exécution.")
