# Déploiement et Tracking MLOps sur EC2

Cette section documente la première implémentation de l'infrastructure de tracking MLOps basée sur **MLflow** et **MinIO**, déployée directement sur une instance **AWS EC2**.

> [!NOTE]
> Nous sommes actuellement dans un environnement EC2 pour tester l'intégration End-to-End.

## Test End-To-End du Workflow sur EC2

Voici la procédure complète pour lancer le tracking, entraîner un modèle et tester l'API de prédiction.

### Étape 1 : Démarrer le serveur de tracking MLflow
On démarre le serveur de tracking sur le port `5002` en tâche de fond. MinIO doit être opérationnel sur le port `9000`.

```bash
export MLFLOW_S3_ENDPOINT_URL=http://127.0.0.1:9000
export AWS_ACCESS_KEY_ID=minioadmin
export AWS_SECRET_ACCESS_KEY=minioadmin
nohup python3 -m mlflow server \
  --backend-store-uri sqlite:///mlflow.db \
  --default-artifact-root s3://mlflow-artifacts \
  --host 0.0.0.0 \
  --port 5002 > mlflow_server.log 2>&1 &
```

### Étape 2 : Entraîner et promouvoir le modèle en Production
Exécution du script d'entraînement pour le modèle de log clustering, avec l'enregistrement automatique du modèle dans le Model Registry MLflow.

```bash
export MLFLOW_TRACKING_URI=http://127.0.0.1:5002
python3 ML/ML_Log_Loki/scripts/train_log_clustering.py --register-model=true --promote-to-production=true
```

### Étape 3 : Démarrer le serveur API de prédiction MLflow
Exposition du modèle promu en production via une API REST sur le port `5001`.

```bash
nohup python3 -m mlflow models serve \
  -m "models:/log-clustering-kmeans/Production" \
  -p 5001 --env-manager local > mlflow_api_serve.log 2>&1 &
```

### Étape 4 : Tester l'API avec de nouveaux logs
Dans un autre terminal, test de l'API déployée avec `curl` :

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

La réponse devrait être un JSON contenant le `cluster_id` et le `cluster_label` pour chaque log fourni en entrée.
