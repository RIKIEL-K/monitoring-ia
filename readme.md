
Ce guide détaille le déploiement d'une infrastructure MLOps minimale sur Kubernetes pour stocker les artefacts (MinIO) et centraliser le tracking (MLflow).

## 1. Déployer MinIO

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
Ouvrez `http://localhost:9001` (ou `http://<node-ip>:9001`).
- Username : `minioadmin`
- Password : `minioadmin`

> [!IMPORTANT]
> **Créez le bucket `mlartifacts`** dans l'UI de MinIO avant de déployer MLflow.

## 2. Déployer MLflow

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
Ouvrez `http://localhost:5002` (ou `http://<node-ip>:5002`).

## 3. Entraîner et promouvoir le modèle en Production

Exportez les variables d'environnement pointant vers vos services K8s, puis lancez l'entraînement :

```bash
export MLFLOW_TRACKING_URI="http://localhost:5002" # Ou http://mlflow-service:5000 dans le cluster
export MLFLOW_S3_ENDPOINT_URL="http://localhost:9000" # Ou http://minio-service:9000 dans le cluster
export AWS_ACCESS_KEY_ID="minioadmin"
export AWS_SECRET_ACCESS_KEY="minioadmin"

python3 ML_Log_Loki/scripts/train_log_clustering.py --register-model=true --promote-to-production=true
```

## 4. Démarrer le serveur API de prédiction MLflow en tâche de fond

```bash
nohup python3 -m mlflow models serve -m "models:/log-clustering-kmeans/Production" -p 5001 --env-manager local > mlflow_api_serve.log 2>&1 &
```

## 5. Tester l'API avec de nouveaux logs

```bash
curl -X POST -H "Content-Type: application/json" -d '{
  "dataframe_split": {
    "columns": ["message"],
    "data": [
      ["level=error msg=\"timeout connection to database\""],
      ["level=info user=admin action=login success=true"]
    ]
  }
}' http://localhost:5001/invocations
```
*(La réponse devrait être un JSON contenant le cluster_id et le cluster_label pour chaque log)*

## 6. Accès distant aux UIs (Tunnel SSH)

Pour afficher les interfaces web (MinIO et MLflow) sur votre navigateur Chrome en local alors que tout tourne sur une machine EC2 distante, la méthode la plus fiable et la plus sécurisée (sans avoir à modifier les pare-feux d'AWS) est de créer un Tunnel SSH.

Voici les 2 étapes simples à suivre :

**Étape 1 : Sur votre instance EC2**
Vous devez d'abord relayer les ports du cluster K8s vers le réseau local (localhost) de votre instance EC2. Tapez ces deux commandes (elles s'exécuteront en arrière-plan) :

```bash
kubectl port-forward --address 127.0.0.1 svc/minio-service 9001:9001 &
kubectl port-forward --address 127.0.0.1 svc/mlflow-service 5002:5000 &
```

**Étape 2 : Sur votre machine locale (Windows)**
Ouvrez un nouveau terminal (Invite de commandes ou PowerShell) sur votre propre ordinateur et connectez-vous à votre EC2 avec cette commande spéciale qui va lier les ports de l'EC2 à ceux de votre PC :

```bash
ssh -i "C:\chemin\vers\votre_cle.pem" -L 9001:127.0.0.1:9001 -L 5002:127.0.0.1:5002 ubuntu@<IP_PUBLIQUE_DE_VOTRE_EC2>
```
*(Remplacez le chemin de la clé .pem et <IP_PUBLIQUE_DE_VOTRE_EC2> par vos vraies valeurs).*

**Étape 3 : Sur votre navigateur Chrome**
Tant que la fenêtre SSH de l'Étape 2 reste ouverte, votre tunnel fonctionne ! Ouvrez simplement Chrome sur votre ordinateur et allez sur :

- **MinIO** : http://localhost:9001
- **MLflow** : http://localhost:5002

## 3. Exécution du Job d'entraînement dans Kubernetes

Le but est d'exécuter l'entraînement en batch via Kubernetes, et de logger automatiquement les paramètres, les métriques et le modèle dans MLflow tout en stockant les artefacts dans MinIO.

**Soumettre le Job :**
```bash
kubectl apply -f manifests/training-job.yaml
```

**Suivre les logs :**
```bash
kubectl logs -l app=training -f
```

*(La sortie attendue devrait indiquer la fin de l'entraînement et "Model logged to MLflow")*

> [!WARNING]
> **Dépannage : Pod bloqué en ContainerCreating (hostPath type check failed)**
> 
> Comme Minikube tourne isolé dans son propre conteneur Docker, le chemin `/home/ubuntu/monitoring-ia` (qui est sur votre EC2) n'existe pas à l'intérieur de Minikube. Il refuse donc de démarrer le pod.
> La solution est de "monter" (partager) ce dossier depuis l'EC2 vers Minikube en utilisant une commande spécifique de Minikube.
> 
> Voici les 3 étapes rapides pour corriger cela sur votre EC2 :
> 
> **1. Lancer le partage de dossier (en tâche de fond avec le `&` à la fin) :**
> ```bash
> minikube mount /home/ubuntu/monitoring-ia:/home/ubuntu/monitoring-ia &
> ```
> *(Laissez cette commande tourner. Elle vous affichera probablement un message indiquant que le montage est réussi).*
> 
> **2. Supprimer le Job bloqué :**
> ```bash
> kubectl delete -f manifests/training-job.yaml
> ```
> 
> **3. Relancer le Job proprement :**
> ```bash
> kubectl apply -f manifests/training-job.yaml
> ```
> Cette fois-ci, le pod trouvera bien le dossier contenant vos scripts Python et l'entraînement pourra commencer !


## 4. Vérification dans MLflow UI

Le script gère automatiquement l'enregistrement et la promotion en production !
1. Ouvrez l'UI MLflow (`http://localhost:5002`).
2. Allez à l'expérience **loki-prod** et vérifiez le nouveau *run*.
3. Vous verrez que votre modèle `log-clustering-kmeans` a été automatiquement promu en `Production`.

## 5. Conteneurisation du service de Serving (Docker)

Le but est d'empaqueter le serveur de prédiction MLflow dans une image Docker réutilisable pour servir le modèle enregistré.
Un `Dockerfile` est déjà préparé à la racine du projet.

**Construire l'image :**
```bash
docker build -t loki-kmeans-serve:v1 .
docker images | grep loki-kmeans-serve
```

**Tester l'image localement :**
```bash
# Vérifier la version de MLflow dans l'image
docker run --rm loki-kmeans-serve:v1 mlflow --version

# Vérifier la commande par défaut de l'image
docker inspect loki-kmeans-serve:v1 --format='{{.Config.Cmd}}'
```

## 6. Déploiement de l'API de Prédiction (Serving)

Une fois l'image construite, déployez le `Deployment` et le `Service` NodePort dans Kubernetes :

```bash
kubectl apply -f manifests/model-deployment.yaml
kubectl apply -f manifests/model-service.yaml
```

**Suivre le démarrage des pods :**
```bash
kubectl get pods -l app=model-serving -w
```
*(Attendez que les pods passent en statut `Running` avec `READY 1/1`. Le démarrage peut prendre environ 30 secondes le temps que le modèle soit téléchargé depuis MinIO).*

## 7. Tests de l'API

Une fois les pods prêts, vous pouvez tester l'API qui est exposée sur le port `30501` par le Service NodePort.

**Vérifier la santé de l'API :**
```bash
curl http://localhost:30501/ping
```
*(Attendu: 200 OK ou réponse vide, cela prouve que le modèle est bien chargé en mémoire).*

**Tester une prédiction :**
```bash
# Exemple avec des logs textuels
curl -X POST http://localhost:30501/invocations \
-H "Content-Type: application/json" \
-d '{
  "dataframe_split": {
    "columns": ["message"],
    "data": [
      ["level=error msg=\"timeout connection to database\""],
      ["level=info user=admin action=login success=true"]
    ]
  }
}'
```
*(Attendu : un JSON contenant le cluster associé à chaque ligne de log).*

## Bonnes Pratiques de Production

> [!WARNING]
> Ce déploiement est conçu pour un environnement de développement ou de laboratoire.

Pour la production, veuillez considérer :
- **Stockage** : Utiliser des PersistentVolumeClaims (PVC) avec provisionnement dynamique au lieu de `hostPath`.
- **Secrets** : Stocker `AWS_ACCESS_KEY_ID` et `AWS_SECRET_ACCESS_KEY` dans des Kubernetes Secrets.
- **Backend MLflow** : Remplacer SQLite par une base de données PostgreSQL pour gérer la concurrence.
- **Réseau** : Utiliser un Ingress controller avec TLS pour sécuriser les accès (au lieu de `NodePort`).
- **Haute disponibilité** : Utiliser MinIO en mode distribué ou une solution Cloud managée (AWS S3, GCP GCS).

## 8. Déploiement de la Stack MLOps complète (MinIO, MLflow, Kubeflow)

Kubeflow Pipelines (KFP) permet d'orchestrer, déployer et gérer des workflows de Machine Learning.
L'environnement complet (MinIO, MLflow, CRDs, manifests, NodePort UI) est automatisé via un script de déploiement global.

**1. Préparer les données d'entraînement :**
Placez votre dataset `fitness_data.csv` dans le dossier local (par exemple `/root/code/data/`).
Déployez ensuite le Volume Persistant (PV) et sa réservation (PVC) pour rendre les données accessibles à Kubeflow :
```bash
kubectl apply -f manifests/data-pv.yaml
```

**2. Lancer l'installation automatisée de la Stack :**
```bash
chmod +x deploy_stack.sh
./deploy_stack.sh
```
*(Le script déploie MinIO, crée le bucket, déploie MLflow, puis installe Kubeflow. L'attente du démarrage des pods peut prendre de 5 à 10 minutes).*

**3. Accéder à l'interface de Kubeflow (UI) :**
L'interface est exposée sur le port `30502`. Ouvrez un tunnel SSH si vous êtes sur une machine EC2 distante :
```bash
ssh -i "C:\chemin\vers\votre_cle.pem" -L 30502:127.0.0.1:30502 ubuntu@<IP_PUBLIQUE_DE_VOTRE_EC2>
```
Accédez ensuite à l'UI via http://localhost:30502.

**4. Tester l'intégration entre Kubeflow et MLflow :**
Un workflow Argo de test a été préparé pour vérifier la connexion :
```bash
kubectl apply -f manifests/kubeflow/mlflow-integration-check.yaml
```
Vous pouvez suivre l'exécution de ce test directement depuis l'interface UI de Kubeflow.
