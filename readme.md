# Déploiement MLOps avec Kubeflow sur Kubernetes

Ce projet fournit une infrastructure MLOps complète sur Kubernetes. Il met en place les fondations de stockage (MinIO) et de tracking (MLflow), pour ensuite orchestrer les entraînements et les déploiements de manière avancée via **Kubeflow Pipelines**.

---

## Démarrage Rapide

Voici les commandes essentielles pour déployer l'infrastructure globale sur votre cluster :

### 1. Préparer les données
Déployez le Volume Persistant (PV) pour rendre les données accessibles à Kubeflow :
```bash
kubectl apply -f manifests/data-pv.yaml
```

### 2. Lancer l'installation automatisée de la Stack
Le script suivant déploie MinIO, crée les buckets, déploie MLflow, puis installe Kubeflow :
```bash
chmod +x deploy_stack.sh
./deploy_stack.sh
```
*(L'attente du démarrage complet de tous les pods peut prendre de 5 à 10 minutes).*

---

## Documentation Complète

Pour conserver un dépôt clair, l'ensemble de la documentation détaillée concernant la création des **Pipelines Kubeflow**, l'utilisation de l'interface, la conteneurisation, la configuration des tunnels SSH et le dépannage des erreurs a été centralisée sur **MkDocs**.

Pour consulter l'intégralité du guide de déploiement et d'utilisation, lancez simplement la commande suivante à la racine du projet :

```bash
mkdocs serve
```

Puis ouvrez `http://localhost:8000` dans votre navigateur.
