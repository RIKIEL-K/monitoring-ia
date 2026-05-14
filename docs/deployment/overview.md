# Vue d'ensemble du déploiement

## Prérequis

- Kubernetes (Minikube) opérationnel sur l'EC2
- Client `mc` (MinIO Client) installé sur l'EC2

```bash
# Installer le client MinIO
curl https://dl.min.io/client/mc/release/linux-amd64/mc -o /usr/local/bin/mc
sudo chmod +x /usr/local/bin/mc
mc --version
```

## Déploiement en une commande

La stack complète (MinIO + MLflow + Kubeflow) peut être déployée via le script automatisé :

```bash
chmod +x deploy_stack.sh
./deploy_stack.sh
```

L'installation complète peut prendre **5 à 10 minutes** le temps que tous les pods démarrent.

## Déploiement composant par composant

| Ordre | Composant | Section |
|---|---|---|
| 1 | MinIO | [MinIO](minio.md) |
| 2 | MLflow | [MLflow](mlflow.md) |
| 3 | Kubeflow Pipelines | [Kubeflow](kubeflow.md) |

## Ports et accès

| Service | Port interne | NodePort | URL locale |
|---|---|---|---|
| MinIO API | 9000 | 30900 | `http://localhost:30900` |
| MinIO UI | 9001 | 30901 | `http://localhost:30901` |
| MLflow | 5000 | 30500 | `http://localhost:30500` |
| Kubeflow UI | - | 30502 | `http://localhost:30502` |
| API Serving | - | 30501 | `http://localhost:30501` |

!!! tip "Accès depuis une machine locale"
    Si votre cluster tourne sur une EC2 distante, consultez la section **[Tunnel SSH](../access/ssh-tunnel.md)** pour accéder aux UIs depuis votre navigateur.
