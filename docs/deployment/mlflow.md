# Déploiement MLflow

MLflow est le serveur de tracking des expériences ML et le Model Registry.

## Déploiement

```bash
kubectl apply -f manifests/mlflow-deployment.yaml
kubectl apply -f manifests/mlflow-service.yaml
```

## Vérification

```bash
kubectl get pods -l app=mlflow
kubectl get svc mlflow-service
kubectl logs -l app=mlflow -f
```

## Accès à l'UI MLflow

Ouvrez `http://localhost:30500`.

## Entraîner et enregistrer un modèle

```bash
# Variables d'environnement
export MLFLOW_TRACKING_URI="http://localhost:30500"
export MLFLOW_S3_ENDPOINT_URL="http://localhost:30900"
export AWS_ACCESS_KEY_ID="minioadmin"
export AWS_SECRET_ACCESS_KEY="minioadmin"

# Lancer l'entraînement
python3 ML_Log_Loki/scripts/train_log_clustering.py \
  --register-model=true \
  --promote-to-production=true
```

## Promouvoir un modèle manuellement

!!! warning "Promotion manuelle"
    La promotion Staging → Production est **volontairement manuelle**. Utilisez l'UI MLflow (`http://localhost:30500`) pour promouvoir une version après validation humaine.
