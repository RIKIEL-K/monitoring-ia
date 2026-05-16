# Script de déploiement automatisé

Le script `deploy_stack.sh` automatise l'installation complète de la stack MLOps.

## Utilisation

```bash
chmod +x deploy_stack.sh
./deploy_stack.sh
```

## Ce que fait le script

1. Déploie **MinIO** et crée les buckets nécessaires (`mlartifacts`, `mlpipeline`)
2. Déploie **MLflow** connecté à MinIO
3. Installe **Kubeflow Pipelines** avec la configuration RBAC
4. Attend que tous les pods soient `Running`

## Durée estimée

| Étape | Temps estimé |
|---|---|
| MinIO | ~1 minute |
| MLflow | ~1 minute |
| Kubeflow | 5 à 10 minutes |
| **Total** | **~12 minutes** |
