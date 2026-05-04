
# ===================================================================
# 🚀 DÉPLOIEMENT ET TEST END-TO-END SUR KUBERNETES
# ===================================================================

Ce guide détaille le déploiement d'une infrastructure MLOps minimale sur Kubernetes pour stocker les artefacts (MinIO) et centraliser le tracking (MLflow).

## 1. Déployer MinIO

Appliquez les manifestes pour déployer MinIO :

```bash
kubectl apply -f manifests/minio-deployment.yaml
kubectl apply -f manifests/minio-service.yaml
```

Vérifiez le déploiement :

```bash
kubectl get pods -l app=minio
kubectl get svc minio-service
kubectl wait --for=condition=ready pod -l app=minio --timeout=120s
```

**Accéder à l'UI MinIO :**
Ouvrez `http://localhost:30901` (ou `http://<node-ip>:30901`).
- Username : `minioadmin`
- Password : `minioadmin`

> [!IMPORTANT]
> **Créez le bucket `mlartifacts`** dans l'UI de MinIO avant de déployer MLflow.

## 2. Déployer MLflow

Appliquez les manifestes pour déployer MLflow :

```bash
kubectl apply -f manifests/mlflow-deployment.yaml
kubectl apply -f manifests/mlflow-service.yaml
```

Vérifiez le déploiement :

```bash
kubectl get pods -l app=mlflow
kubectl get svc mlflow-service
kubectl logs -l app=mlflow -f
```

**Accéder à l'UI MLflow :**
Ouvrez `http://localhost:30500` (ou `http://<node-ip>:30500`).

## 3. Entraîner et promouvoir le modèle en Production

Exportez les variables d'environnement pointant vers vos services K8s, puis lancez l'entraînement :

```bash
export MLFLOW_TRACKING_URI="http://localhost:30500" # Ou http://mlflow-service:5000 dans le cluster
export MLFLOW_S3_ENDPOINT_URL="http://localhost:30900" # Ou http://minio-service:9000 dans le cluster
export AWS_ACCESS_KEY_ID="minioadmin"
export AWS_SECRET_ACCESS_KEY="minioadmin"

python3 ML_Log_Loki/scripts/train_log_clustering.py --register-model=true --promote-to-production=true
```

## 4. Démarrer le serveur API de prédiction MLflow en tâche de fond

```bash
nohup python3 -m mlflow models serve -m "models:/log-clustering-kmeans/Production" -p 5001 --env-manager local > mlflow_api_serve.log 2>&1 &
```

## 5. Tester l'API avec de nouveaux logs

```bash
curl -X POST -H "Content-Type: application/json" -d '{
  "dataframe_split": {
    "columns": ["message"],
    "data": [
      ["level=error msg=\"timeout connection to database\""],
      ["level=info user=admin action=login success=true"]
    ]
  }
}' http://localhost:5001/invocations
```
*(La réponse devrait être un JSON contenant le cluster_id et le cluster_label pour chaque log)*

## Bonnes Pratiques de Production

> [!WARNING]
> Ce déploiement est conçu pour un environnement de développement ou de laboratoire.

Pour la production, veuillez considérer :
- **Stockage** : Utiliser des PersistentVolumeClaims (PVC) avec provisionnement dynamique au lieu de `hostPath`.
- **Secrets** : Stocker `AWS_ACCESS_KEY_ID` et `AWS_SECRET_ACCESS_KEY` dans des Kubernetes Secrets.
- **Backend MLflow** : Remplacer SQLite par une base de données PostgreSQL pour gérer la concurrence.
- **Réseau** : Utiliser un Ingress controller avec TLS pour sécuriser les accès (au lieu de `NodePort`).
- **Haute disponibilité** : Utiliser MinIO en mode distribué ou une solution Cloud managée (AWS S3, GCP GCS).

