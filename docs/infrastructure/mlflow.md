# Déployer MLflow

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

## Vérification dans MLflow UI

Le script d'entraînement gère automatiquement l'enregistrement et la promotion en production !

1. Ouvrez l'UI MLflow (`http://localhost:30500`).
2. Allez à l'expérience **loki-prod** et vérifiez le nouveau *run*.
3. Vous verrez que votre modèle `log-clustering-kmeans` a été automatiquement promu en `Production`.
