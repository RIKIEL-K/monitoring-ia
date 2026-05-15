# Documentation MLOps

Bienvenue dans la documentation de l'infrastructure **MLOps** du projet `monitoring-ia`. Cette documentation couvre le déploiement, la configuration, l'utilisation des pipelines et la résolution des erreurs courantes.

## Architecture globale

```
┌─────────────────────────────────────────────────────┐
│                     Kubernetes (Minikube / EC2)      │
│                                                     │
│  ┌──────────┐   ┌──────────┐   ┌────────────────┐  │
│  │  MinIO   │   │  MLflow  │   │    Kubeflow    │  │
│  │ :9000    │◄──│ :5000    │◄──│  Pipelines     │  │
│  │ :9001 UI │   │ :30500   │   │  :30502 UI     │  │
│  └──────────┘   └──────────┘   └────────────────┘  │
│       ▲                                ▲            │
│       │         Artefacts ML           │            │
│       └────────────────────────────────┘            │
└─────────────────────────────────────────────────────┘
```

## Composants

| Composant | Rôle | Port NodePort |
|---|---|---|
| **MinIO** | Stockage des artefacts ML (modèles, datasets) | `30900` (API), `30901` (UI) |
| **MLflow** | Tracking des expériences & Model Registry | `30500` |
| **Kubeflow Pipelines** | Orchestration des workflows ML | `30502` |
| **API Serving** | Prédictions en temps réel (log-clustering) | `30501` |

## Démarrage rapide

```bash
# 1. Déployer toute la stack
./deploy_stack.sh

# 2. Accéder aux UIs (via tunnel SSH si EC2)
# MinIO  → http://localhost:30901
# MLflow → http://localhost:30500
# Kubeflow → http://localhost:30502

# 3. Lancer le pipeline de clustering de logs
cd ml/ml-log-loki/kubeflow
python pipeline.py
```

## Navigation

- **[Déploiement](deployment/overview.md)** — Installer et configurer les composants
- **[Pipelines ML](pipelines/log-clustering.md)** — Utiliser les pipelines Kubeflow
- **[Accès distant](access/ssh-tunnel.md)** — Se connecter depuis une machine locale
- **[Troubleshooting](troubleshooting/index.md)** — Résoudre les erreurs courantes

!!! tip "Première installation ?"
    Commencez par la section **[Déploiement → Vue d'ensemble](deployment/overview.md)** pour déployer la stack complète en une seule commande.
