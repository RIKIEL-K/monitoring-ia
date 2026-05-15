# Déployer MinIO

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

!!! important "Configuration de MinIO"
    **Créez le bucket `mlartifacts`** dans l'UI de MinIO avant de déployer MLflow.
