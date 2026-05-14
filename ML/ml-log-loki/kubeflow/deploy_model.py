"""
Log Clustering Pipeline — Déploiement serving (patch image sur un Deployment).

Écrit un Dockerfile de référence sur un PVC (traçabilité), puis met à jour
l'image du conteneur cible via JSON Patch (sans écraser la liste des conteneurs).

Prérequis cluster: le pod du pipeline doit pouvoir patcher les Deployments
(Role + RoleBinding sur le ServiceAccount d'exécution des pipelines).
"""

from kfp import dsl


@dsl.component(
    packages_to_install=["kubernetes"],
    base_image="python:3.12-slim",
)
def deploy_model(
    mlflow_tracking_uri: str,
    minio_endpoint: str,
    aws_access_key: str,
    aws_secret_key: str,
    model_name: str,
    model_version: str,
    deployment_name: str,
    deployment_namespace: str,
    container_name: str,
    base_image: str,
    image_tag: str,
) -> str:
    """
    Met à jour un Deployment Kubernetes pour pointer vers new_image.

    Le Dockerfile généré sous /artifacts documente la commande mlflow models serve
    pour models:/{model_name}/{model_version} (build image hors pipeline, ex. CI).
    """
    import os
    from kubernetes import client, config
    from kubernetes.client.exceptions import ApiException

    new_image = f"{base_image}:{image_tag}"
    print(f"Déploiement modèle {model_name} version {model_version}")
    print(f"Cible: {deployment_namespace}/{deployment_name}, conteneur={container_name}")
    print(f"Nouvelle image: {new_image}")

    # ── Dockerfile de référence (traçabilité dans les logs du pod) ────────────
    dockerfile_content = f"""# Généré par le pipeline Kubeflow (ml-log-loki)
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir mlflow==2.16.2 scikit-learn==1.5.2 pandas boto3
ENV MLFLOW_TRACKING_URI={mlflow_tracking_uri}
ENV MLFLOW_S3_ENDPOINT_URL={minio_endpoint}
ENV AWS_ACCESS_KEY_ID={aws_access_key}
ENV AWS_SECRET_ACCESS_KEY={aws_secret_key}
ENV MODEL_NAME={model_name}
ENV MODEL_VERSION={model_version}
EXPOSE 5001
CMD ["mlflow", "models", "serve", "-m", "models:/{model_name}/{model_version}", "-h", "0.0.0.0", "-p", "5001", "--env-manager=local"]
"""
    artifacts_dir = "/tmp/kfp-deploy-artifacts"
    os.makedirs(artifacts_dir, exist_ok=True)
    safe_name = model_name.replace("/", "-")
    dockerfile_path = os.path.join(artifacts_dir, f"Dockerfile.{safe_name}.v{model_version}")
    with open(dockerfile_path, "w", encoding="utf-8") as f:
        f.write(dockerfile_content)
    print(f"Dockerfile de référence : {dockerfile_path}")

    # ── Connexion à l'API Kubernetes (in-cluster) ─────────────────────────────
    config.load_incluster_config()
    apps_v1 = client.AppsV1Api()

    # ── Pattern UPSERT : crée le Deployment s'il n'existe pas, le patche sinon ─
    try:
        dep = apps_v1.read_namespaced_deployment(deployment_name, deployment_namespace)

        # ── CAS 1 : Deployment existant → patch de l'image uniquement ──────────
        containers = dep.spec.template.spec.containers
        idx = next(
            (i for i, c in enumerate(containers) if c.name == container_name),
            None
        )
        if idx is None:
            names = [c.name for c in containers]
            raise ValueError(
                f"Conteneur {container_name!r} introuvable dans le Deployment. "
                f"Conteneurs disponibles : {names}"
            )

        patch = [{"op": "replace",
                  "path": f"/spec/template/spec/containers/{idx}/image",
                  "value": new_image}]
        apps_v1.patch_namespaced_deployment(
            name=deployment_name,
            namespace=deployment_namespace,
            body=patch,
            content_type="application/json-patch+json",
        )
        action = "patché (rolling update déclenché)"

    except ApiException as e:
        if e.status != 404:
            raise  # Autre erreur (403, 500...) → on propage

        # ── CAS 2 : Deployment absent → création complète ──────────────────────
        print(f"  Deployment '{deployment_name}' introuvable → création...")
        deployment_manifest = client.V1Deployment(
            api_version="apps/v1",
            kind="Deployment",
            metadata=client.V1ObjectMeta(
                name=deployment_name,
                namespace=deployment_namespace,
                labels={"app": deployment_name, "managed-by": "kubeflow-pipeline"},
            ),
            spec=client.V1DeploymentSpec(
                replicas=1,
                selector=client.V1LabelSelector(
                    match_labels={"app": deployment_name}
                ),
                template=client.V1PodTemplateSpec(
                    metadata=client.V1ObjectMeta(
                        labels={"app": deployment_name}
                    ),
                    spec=client.V1PodSpec(
                        containers=[
                            client.V1Container(
                                name=container_name,
                                image=new_image,
                                ports=[client.V1ContainerPort(container_port=5001)],
                                env=[
                                    client.V1EnvVar("MLFLOW_TRACKING_URI",   mlflow_tracking_uri),
                                    client.V1EnvVar("MLFLOW_S3_ENDPOINT_URL", minio_endpoint),
                                    client.V1EnvVar("AWS_ACCESS_KEY_ID",     aws_access_key),
                                    client.V1EnvVar("AWS_SECRET_ACCESS_KEY", aws_secret_key),
                                    client.V1EnvVar("MODEL_NAME",            model_name),
                                    client.V1EnvVar("MODEL_VERSION",         model_version),
                                ],
                            )
                        ]
                    ),
                ),
            ),
        )
        apps_v1.create_namespaced_deployment(
            namespace=deployment_namespace,
            body=deployment_manifest,
        )
        action = "créé (premier déploiement)"

    result = (
        f"Modèle {model_name} v{model_version} → {deployment_namespace}/"
        f"{deployment_name} [{action}] (image {new_image})"
    )
    print(f"\n[SUCCESS] {result}")
    return result

