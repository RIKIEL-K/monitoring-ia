# Troubleshooting — Vue d'ensemble

Cette section regroupe toutes les erreurs rencontrées lors du déploiement et de l'utilisation de la stack MLOps sur Kubernetes (Kubeflow) (Minikube sur une EC2).

## Méthode de diagnostic générale

Avant de consulter une section spécifique, voici la séquence de diagnostic standard pour un pipeline Kubeflow en erreur :

```bash
# 1. Lister les workflows (runs) actifs ou en erreur
kubectl get workflows -n kubeflow

# 2. Décrire le workflow en échec
kubectl describe workflow <nom-du-workflow> -n kubeflow | tail -40

# 3. Trouver les pods du workflow
kubectl get pods -n kubeflow -l workflows.argoproj.io/workflow=<nom-du-workflow>

# 4. Lire les logs du pod en erreur
kubectl logs -n kubeflow <nom-du-pod> -c main --tail=100

# 5. Décrire le pod pour avoir l'événement d'erreur
kubectl describe pod <nom-du-pod> -n kubeflow
```

!!! warning "Erreur masquée dans l'UI"
    L'UI Kubeflow affiche parfois des messages génériques comme `Failed to retrieve pod logs`.
    **Toujours** aller lire les logs directement dans le cluster avec `kubectl logs`.
