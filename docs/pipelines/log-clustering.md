# Pipeline Log Clustering (TF-IDF + K-Means)

Le dossier `ml/ml-log-loki/kubeflow/` contient les **composants Kubeflow Pipelines (KFP)** qui transforment le script monolithique `train_log_clustering.py` en un workflow orchestré, tracé et reproductible.

## Architecture & flux de données

```
train_model()  ──── run_id ────►  register_model()
     │                                   │
     ▼                                   ▼
MLflow (params,              MLflow Model Registry
métriques, modèle PyFunc)    (log-clustering-kmeans vX)
     │
     ▼
MinIO S3 (artefacts binaires)
```

## Composants du pipeline

| Étape | Composant | Ce qui se passe |
|---|---|---|
| 1 | `train_model()` | Charge les logs CSV, nettoie, vectorise TF-IDF, entraîne K-Means, évalue le k-range, logue tout dans MLflow, retourne `run_id` |
| 2 | `register_model()` | Reçoit le `run_id`, enregistre le modèle PyFunc dans le Model Registry, retourne `model_version` |

!!! note "Conteneurs isolés"
    Chaque composant s'exécute dans un **conteneur Docker isolé** dans Kubeflow k8s. Toutes les dépendances sont auto-installées via `packages_to_install`.

## Structure des fichiers

```
ml/ml-log-loki/kubeflow/
├── train_model.py              # Composant KFP d'entraînement (TF-IDF + K-Means)
├── register_model.py           # Composant KFP d'enregistrement (Model Registry)
└── pipeline.py                 # Definition du pipeline + compilation YAML
```

## Paramètres configurables

| Paramètre | Défaut | Description |
|---|---|---|
| `mlflow_tracking_uri` | `http://mlflow-service:5000` | URL du serveur MLflow |
| `minio_endpoint` | `http://minio-service:9000` | URL de MinIO |
| `experiment_name` | `log-clustering-loki` | Nom de l'expérience MLflow |
| `data_path` | `/data/mock_loki_logs.csv` | Chemin du dataset |
| `n_clusters` | `5` | Nombre de clusters K-Means |
| `max_features` | `100` | Taille du vocabulaire TF-IDF |
| `k_range` | `3,5,8,10,12,15` | Valeurs k à évaluer (elbow + silhouette) |
| `random_state` | `42` | Seed de reproductibilité |
| `model_name` | `log-clustering-kmeans` | Nom dans le Model Registry |

## Utilisation

### 1. Compiler le pipeline en YAML

```bash
cd ml/ml-log-loki/kubeflow
python pipeline.py
# Génère log_clustering_pipeline.yaml
```

### 2. Soumettre à Kubeflow

Via l'UI Kubeflow (`http://localhost:30502`) ou via la CLI :

```bash
kfp pipeline create \
  --pipeline-name "log-clustering-pipeline" \
  log_clustering_pipeline.yaml
```

### 3. Lancer un Run avec des paramètres personnalisés

Dans l'UI Kubeflow → **Pipelines** → **Create Run**, modifiez les paramètres sans toucher au code.

## Erreurs fréquentes

| Erreur | Solution |
|---|---|
| `FileNotFoundError: /data/mock_loki_logs.csv` | [Troubleshooting D](../troubleshooting/d-file-not-found.md) |
| Timeout `seaweedfs.kubeflow:9000` après l'entraînement | [Troubleshooting E](../troubleshooting/e-seaweedfs-timeout.md) |
| `Error 3988` / emojis dans le code | [Troubleshooting B](../troubleshooting/b-mysql-collation.md) |
