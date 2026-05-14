# Déploiement MinIO

MinIO est le stockage des artefacts ML (modèles, datasets) compatible S3.

## Déploiement

```bash
kubectl apply -f manifests/minio-deployment.yaml
kubectl apply -f manifests/minio-service.yaml
```

## Vérification

```bash
kubectl get pods -l app=minio
kubectl get svc minio-service
kubectl wait --for=condition=ready pod -l app=minio --timeout=120s
```

## Accès à l'UI MinIO

Ouvrez `http://localhost:30901` (ou `http://<node-ip>:30901`).

- **Username** : `minioadmin`
- **Password** : `minioadmin`

!!! important "Créer le bucket `mlartifacts`"
    Avant de déployer MLflow, créez le bucket `mlartifacts` dans l'UI de MinIO.

## Créer des buckets via la CLI

```bash
# Configurer l'alias
mc alias set local http://localhost:30900 minioadmin minioadmin

# Créer les buckets nécessaires
mc mb local/mlartifacts
mc mb local/mlpipeline

# Vérifier
mc ls local/
```
