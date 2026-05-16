# Prédictions & Serving

Cette page explique comment utiliser le modèle enregistré pour faire des prédictions.

## Option A — Via `mlflow models serve`

```bash
export MLFLOW_TRACKING_URI="http://localhost:30500"
export MLFLOW_S3_ENDPOINT_URL="http://localhost:30900"
export AWS_ACCESS_KEY_ID="minioadmin"
export AWS_SECRET_ACCESS_KEY="minioadmin"

mlflow models serve \
  -m "models:/log-clustering-kmeans/1" \
  -p 5001 \
  --no-conda
```

## Option B — Requête de prédiction directe

```bash
curl -X POST http://localhost:5001/invocations \
  -H "Content-Type: application/json" \
  -d '{
    "dataframe_records": [
      {"message": "level=error msg=connection refused endpoint=/api/orders"},
      {"message": "level=info msg=request processed status=200"}
    ]
  }'
```

Réponse attendue :

```json
[
  {"cluster_id": 2, "cluster_label": "Erreurs Serveur (api)"},
  {"cluster_id": 0, "cluster_label": "Operations Api (/api/orders)"}
]
```

## Option C — Intégration Python (AIOps)

```python
import mlflow.pyfunc, pandas as pd, os

os.environ["MLFLOW_S3_ENDPOINT_URL"] = "http://localhost:30900"
os.environ["AWS_ACCESS_KEY_ID"]      = "minioadmin"
os.environ["AWS_SECRET_ACCESS_KEY"]  = "minioadmin"

model = mlflow.pyfunc.load_model("models:/log-clustering-kmeans/1")

logs = pd.DataFrame({"message": [
    "level=error msg='timeout' endpoint=/api/payments",
    "level=warn msg='high latency' response_time=2500ms"
]})

print(model.predict(logs))
```

## Déploiement en production (Kubeflow k8s)

```bash
# Construire l'image Docker
docker build -t loki-kmeans-serve:v1 .

# Déployer dans Kubernetes
kubectl apply -f manifests/model-deployment.yaml
kubectl apply -f manifests/model-service.yaml

# Suivre le démarrage
kubectl get pods -l app=model-serving -w
```

Tester l'API :

```bash
# Health check
curl http://localhost:30501/ping

# Prédiction
curl -X POST http://localhost:30501/invocations \
  -H "Content-Type: application/json" \
  -d '{"dataframe_split": {"columns": ["message"], "data": [["level=error timeout"]]}}'
```

## Flux AIOps complet

```
Loki (nouveaux logs)
        │
        ▼
  collecte CSV / stream
        │
        ▼
  API FastAPI / mlflow serve
        │  model.predict()
        ▼
  cluster_id + cluster_label
        │
        ├── cluster "Erreurs Serveur"     → Alertmanager → PagerDuty
        ├── cluster "Acces Non Autorises" → alerte sécurité
        └── cluster "Operations normales" → pas d'alerte
```
