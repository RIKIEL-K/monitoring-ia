# Déploiement MLOps sur Kubernetes

Ce projet fournit l'infrastructure, les scripts et les pipelines nécessaires pour un déploiement MLOps complet sur Kubernetes. Il inclut le stockage des artefacts avec **MinIO**, le tracking des expériences et des modèles avec **MLflow**, l'orchestration des entraînements via des Batch Jobs Kubernetes, et le déploiement du modèle final sous forme d'API.

---

## Documentation Complète (MkDocs)

La documentation détaillée de l'ensemble du projet (incluant la conteneurisation Docker, les accès distants via SSH, etc) a été migrée vers **MkDocs**.

Pour la consulter en local, exécutez simplement cette commande à la racine du projet :

```bash
mkdocs serve
```

Puis ouvrez **http://localhost:8000** dans votre navigateur.

---

## Démarrage Rapide

Voici les commandes principales pour déployer l'infrastructure de base sur votre cluster Kubernetes. *Pour plus de détails et d'explications, veuillez vous référer à la documentation MkDocs.*

### 1. Déployer MinIO

```bash
kubectl apply -f manifests/minio-deployment.yaml
kubectl apply -f manifests/minio-service.yaml
```

* UI MinIO : port `30901` (`minioadmin` / `minioadmin`).
* **Important** : Créez le bucket `mlartifacts` dans MinIO avant de passer à l'étape suivante.

### 2. Déployer MLflow

```bash
kubectl apply -f manifests/mlflow-deployment.yaml
kubectl apply -f manifests/mlflow-service.yaml
```

* UI MLflow : port `30500`.

### 3. Exécuter l'entraînement dans Kubernetes (Batch Job)

```bash
kubectl apply -f manifests/training-job.yaml
```

Pour suivre l'avancement de l'entraînement :
```bash
kubectl logs -l app=training -f
```
*(Le Job se chargera d'entraîner le modèle, d'enregistrer les paramètres et les métriques dans MLflow, et de sauvegarder le modèle dans MinIO).*

---
*💡 Pour la suite des opérations (déploiement de l'API de prédiction, tests, Kubeflow), lancez la documentation complète avec `mkdocs serve`.*
