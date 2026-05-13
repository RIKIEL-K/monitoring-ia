
Ce guide détaille le déploiement d'une infrastructure MLOps minimale sur Kubernetes pour stocker les artefacts (MinIO) et centraliser le tracking (MLflow).

## Prérequis : Installer le client MinIO (`mc`) sur l'EC2

Le script de déploiement utilise le client `mc` (MinIO Client) installé sur votre machine (l'EC2) pour configurer MinIO et créer le bucket `mlartifacts`.

Si ce n'est pas déjà fait, exécutez ces commandes pour l'installer :

```bash
curl https://dl.min.io/client/mc/release/linux-amd64/mc -o /usr/local/bin/mc
sudo chmod +x /usr/local/bin/mc
mc --version
```

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
Ouvrez `http://localhost:30901` (ou `http://<node-ip>:30901`).
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
Ouvrez `http://localhost:30500` (ou `http://<node-ip>:30500`).

## 3. Entraîner et promouvoir le modèle en Production

Exportez les variables d'environnement pointant vers vos services K8s, puis lancez l'entraînement :

```bash
export MLFLOW_TRACKING_URI="http://localhost:30500" # Ou http://mlflow-service:5000 dans le cluster
export MLFLOW_S3_ENDPOINT_URL="http://localhost:30900" # Ou http://minio-service:9000 dans le cluster
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
kubectl port-forward --address 127.0.0.1 svc/minio-service 30901:9001 &
kubectl port-forward --address 127.0.0.1 svc/mlflow-service 30500:5000 &
```

**Étape 2 : Sur votre machine locale (Windows)**
Ouvrez un nouveau terminal (Invite de commandes ou PowerShell) sur votre propre ordinateur et connectez-vous à votre EC2 avec cette commande spéciale qui va lier les ports de l'EC2 à ceux de votre PC :

```bash
ssh -i "C:\chemin\vers\votre_cle.pem" -L 30901:127.0.0.1:30901 -L 30500:127.0.0.1:30500 ubuntu@<IP_PUBLIQUE_DE_VOTRE_EC2>
```
*(Remplacez le chemin de la clé .pem et <IP_PUBLIQUE_DE_VOTRE_EC2> par vos vraies valeurs).*

**Étape 3 : Sur votre navigateur Chrome**
Tant que la fenêtre SSH de l'Étape 2 reste ouverte, votre tunnel fonctionne ! Ouvrez simplement Chrome sur votre ordinateur et allez sur :

- **MinIO** : http://localhost:30901
- **MLflow** : http://localhost:30500

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
1. Ouvrez l'UI MLflow (`http://localhost:30500`).
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

## 9. Pipeline Kubeflow — Log Clustering (TF-IDF + K-Means)

Le dossier `ml/ml-log-loki/kubeflow/` contient les **composants Kubeflow Pipelines (KFP)** qui transforment le script monolithique `train_log_clustering.py` en un workflow orchestré, tracé et reproductible.

### Architecture & flux de données

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

| Étape | Composant | Ce qui se passe |
|---|---|---|
| 1 | `train_model()` | Charge les logs CSV, nettoie, vectorise TF-IDF, entraîne K-Means, évalue le k-range, logue tout dans MLflow, retourne `run_id` |
| 2 | `register_model()` | Reçoit le `run_id`, enregistre le modèle PyFunc dans le Model Registry, retourne `model_version` |

> [!NOTE]
> Chaque composant s'exécute dans un **conteneur Docker isolé** dans Kubernetes. Toutes les dépendances sont auto-installées via `packages_to_install`. Le script original `train_log_clustering.py` reste intact et fonctionnel.

### Fichiers

```
ml/ml-log-loki/kubeflow/
├── train_model.py              # Composant KFP d'entraînement (TF-IDF + K-Means)
├── register_model.py           # Composant KFP d'enregistrement (Model Registry)
└── pipeline.py                 # Définition du pipeline + compilation YAML
```

### Paramètres configurables du pipeline

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

### 1. Compiler le pipeline en YAML

```bash
cd ml/ml-log-loki/kubeflow
python pipeline.py
# → Génère log_clustering_pipeline.yaml
```

### 2. Soumettre à Kubeflow

Uploadez `log_clustering_pipeline.yaml` dans l'UI Kubeflow (`http://localhost:30502`), ou via la CLI :

```bash
# Via kfp CLI
kfp pipeline create \
  --pipeline-name "log-clustering-pipeline" \
  log_clustering_pipeline.yaml
```

### 3. Lancer un Run avec des paramètres personnalisés

Dans l'UI Kubeflow → **Pipelines** → **Create Run**, vous pouvez modifier tous les paramètres sans toucher au code (ex. : changer `n_clusters` de 5 à 8).

> [!TIP]
> Les données d'entraînement du step `train_model` proviennent du PVC `training-data-pvc` (monté sur `/data` dans le pod). Sur **EC2 + Minikube**, si `/data` est vide ou si vous obtenez un `FileNotFoundError` sur `/data/mock_loki_logs.csv`, suivez le **diagnostic et la solution** décrits en **§10.D** (vérification avec un pod `busybox`, puis `minikube mount`).

### 4. Faire des prédictions après l'enregistrement du modèle

**Option A — Via `mlflow models serve` :**

```bash
export MLFLOW_TRACKING_URI="http://localhost:30500"
export MLFLOW_S3_ENDPOINT_URL="http://localhost:30900"
export AWS_ACCESS_KEY_ID="minioadmin"
export AWS_SECRET_ACCESS_KEY="minioadmin"

mlflow models serve \
  -m "models:/log-clustering-kmeans/1" \
  -p 5001 \
  --no-conda
```

**Option B — Requête de prédiction :**

```bash
curl -X POST http://localhost:5001/invocations \
  -H "Content-Type: application/json" \
  -d '{
    "dataframe_records": [
      {"message": "level=error msg=connection refused endpoint=/api/orders"},
      {"message": "level=info msg=request processed status=200"}
    ]
  }'
```

Réponse attendue :

```json
[
  {"cluster_id": 2, "cluster_label": "Erreurs Serveur (api)"},
  {"cluster_id": 0, "cluster_label": "Opérations Api (/api/orders)"}
]
```

**Option C — Dans un script Python (intégration AIOps) :**

```python
import mlflow.pyfunc, pandas as pd, os

os.environ["MLFLOW_S3_ENDPOINT_URL"] = "http://localhost:30900"
os.environ["AWS_ACCESS_KEY_ID"]      = "minioadmin"
os.environ["AWS_SECRET_ACCESS_KEY"]  = "minioadmin"

model = mlflow.pyfunc.load_model("models:/log-clustering-kmeans/1")

logs = pd.DataFrame({"message": [
    "level=error msg='timeout' endpoint=/api/payments",
    "level=warn msg='high latency' response_time=2500ms"
]})

print(model.predict(logs))
# ┌────────────┬────────────────────────────────────┐
# │ cluster_id │ cluster_label                      │
# ├────────────┼────────────────────────────────────┤
# │ 2          │ Erreurs Serveur (payments)          │
# │ 1          │ Accès Non Autorisés (api)           │
# └────────────┴────────────────────────────────────┘
```

### Flux AIOps complet

```
Loki (nouveaux logs)
        │
        ▼
  collecte CSV / stream
        │
        ▼
  API FastAPI / mlflow serve
        │  model.predict()
        ▼
  cluster_id + cluster_label
        │
        ├── cluster "Erreurs Serveur"   → Alertmanager → PagerDuty
        ├── cluster "Accès Non Autorisés" → alerte sécurité
        └── cluster "Opérations normales" → pas d'alerte
```

> [!WARNING]
> La promotion de stage (Staging → Production) est volontairement **manuelle** dans ce pipeline. Utilisez l'UI MLflow (`http://localhost:30500`) pour promouvoir une version après validation humaine.

## 10. Dépannage : Erreurs courantes Kubeflow Pipelines

### A. Pod bloqué avec `Init:CreateContainerConfigError` (Erreur `runAsNonRoot`)
**Symptôme :** Le pipeline ne démarre pas et `kubectl describe pod <pod-name> -n kubeflow` affiche :
`Error: container has runAsNonRoot and image will run as root`

**Cause :** Kubernetes bloque le conteneur interne d'Argo (`argoexec`) car il tente de se lancer avec les droits "root", ce qui viole la politique de sécurité de Kubeflow.

**Solution :** Forcer l'exécuteur Argo à utiliser un utilisateur standard (8737) en appliquant ce correctif :
```bash
cat << 'EOF' | kubectl apply -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: workflow-controller-configmap
  namespace: kubeflow
data:
  artifactRepository: |
    archiveLogs: true
    s3:
      endpoint: "minio-service.kubeflow:9000"
      bucket: "mlpipeline"
      keyFormat: "private-artifacts/{{workflow.namespace}}/{{workflow.name}}/{{workflow.creationTimestamp.Y}}/{{workflow.creationTimestamp.m}}/{{workflow.creationTimestamp.d}}/{{pod.name}}"
      insecure: true
      accessKeySecret:
        name: mlpipeline-minio-artifact
        key: accesskey
      secretKeySecret:
        name: mlpipeline-minio-artifact
        key: secretkey
  executor: |
    imagePullPolicy: IfNotPresent
    securityContext:
      runAsUser: 8737
      runAsNonRoot: true
EOF

kubectl rollout restart deployment workflow-controller -n kubeflow
```
*Note : Si vous aviez configuré `containerRuntimeExecutor: emissary` manuellement, supprimez-le car il n'est plus supporté dans les versions récentes d'Argo (v3.4+).*

### B. Erreur "Cannot find context" ou "Conversion from collation utf8mb3..." (Erreur 3988)
**Symptôme :** Lors de la création d'un Run, l'interface affiche une erreur interne `InternalServerError` avec un code d'erreur 3988 ou 1366, et les étapes du pipeline sont introuvables (`Cannot find context`).

**Cause :** La base de données MySQL est configurée en `utf8mb3` (pour des raisons de compatibilité d'authentification avec Kubeflow) mais le code de votre composant Python contient des **émojis** (ex: 📦, 🤖, ✅). Le code source des composants étant stocké dans la base MySQL (dans le `PipelineRuntimeManifest`), la présence de caractères sur 4 octets fait planter la base de données.

**Solution :**
1. **Supprimez tous les émojis** ou caractères spéciaux sur 4 octets de vos fichiers Python (`train_model.py`, `register_model.py`, `pipeline.py`).
2. Recompilez le pipeline (`python pipeline.py`).
3. Créez un NOUVEAU Run dans l'interface avec le nouveau fichier YAML compilé.

### C. Suppression bloquée d'un volume persistant (PVC / PV)
**Symptôme :** La commande `kubectl delete pvc ...` reste bloquée indéfiniment ou refuse de mettre à jour le chemin `hostPath`.

**Cause :** Kubernetes place un cadenas de sécurité (`finalizer`) sur les volumes lorsqu'il pense qu'un pod l'utilise encore (même si le pod a planté).

**Solution :** Forcer la suppression du cadenas de sécurité et supprimer le volume brutalement :
```bash
# 1. Faire sauter le cadenas du PVC et le supprimer
kubectl patch pvc training-data-pvc -n kubeflow -p '{"metadata":{"finalizers":null}}'
kubectl delete pvc training-data-pvc -n kubeflow --grace-period=0 --force

# 2. Faire sauter le cadenas du PV et le supprimer
kubectl patch pv training-data-pv -p '{"metadata":{"finalizers":null}}'
kubectl delete pv training-data-pv --grace-period=0 --force

# 3. Recréer le volume proprement
kubectl apply -f manifests/data-pv.yaml
```

### D. Erreur "FileNotFoundError: [Errno 2] No such file or directory: '/data/...'" (pipeline Kubeflow / PVC `training-data-pvc`)

**Symptôme :** L'étape `train_model` échoue avec `FileNotFoundError` sur `/data/mock_loki_logs.csv` (ou autre fichier sous `/data`). Dans l'UI Kubeflow, un message du type « podname argument is required / Failed to retrieve pod logs » peut masquer la vraie erreur : il faut lire les logs côté cluster.

**Cause :** Le manifeste `manifests/data-pv.yaml` expose les données via un `hostPath` (ex. `/home/ubuntu/monitoring-ia/ML/ml-log-loki/datasets` sur le nœud). Sur une **EC2 avec Minikube**, ce chemin sur le disque de l'EC2 **n'est pas le même** que le système de fichiers **à l'intérieur** de la VM Minikube : le répertoire peut être absent ou **vide** dans le pod malgré des fichiers présents sur l'hôte Ubuntu. Le montage PVC fonctionne, mais le contenu vu sous `/data` est vide.

#### Diagnostic (sur l'EC2)

1. **Identifier le workflow et le pod du step en échec** (namespace `kubeflow` si vos runs y sont créés) :
   ```bash
   kubectl get workflows -n kubeflow
   kubectl describe workflow <nom-du-workflow> -n kubeflow | tail -40
   kubectl get pods -n kubeflow -l workflows.argoproj.io/workflow=<nom-du-workflow>
   ```

2. **Lire les logs du conteneur d'exécution** (pod `...-system-container-impl-...`, conteneur `main` en général) :
   ```bash
   kubectl logs -n kubeflow <nom-du-pod-impl> -c main --tail=-1 | head -80
   ```
   Vous y verrez la trace Python complète (`FileNotFoundError`, etc.).

3. **Vérifier que le PVC est bien monté et ce qu'il contient** (indépendamment du pipeline) :
   ```bash
   kubectl run -it --rm pvc-check --restart=Never -n kubeflow \
     --image=busybox \
     --overrides='{"spec":{"containers":[{"name":"c","image":"busybox","stdin":true,"tty":true,"command":["sh"],"volumeMounts":[{"mountPath":"/data","name":"v"}]}],"volumes":[{"name":"v","persistentVolumeClaim":{"claimName":"training-data-pvc"}}]}}' -- sh
   ```
   Dans le shell du pod : `ls -la /data` puis `head -3 /data/mock_loki_logs.csv`.
   - Si `/data` est **vide** alors que les fichiers existent sur l'EC2 sous le chemin du `hostPath` : c'est bien le cas **Minikube sans partage** (voir solution ci-dessous).
   - Si les fichiers **apparaissent** après correction : relancez un **nouveau run** du pipeline.

4. **Contrôle sur l'hôte Ubuntu** (hors pod) : le CSV doit exister au chemin absolu défini dans le PV (`hostPath` dans `manifests/data-pv.yaml`), par exemple :
   ```bash
   ls -la /home/ubuntu/monitoring-ia/ML/ml-log-loki/datasets/mock_loki_logs.csv
   ```

#### Solution : partager le dépôt EC2 avec Minikube (`minikube mount`)

1. Sur l'EC2, lancez le partage **en tâche de fond** (adaptez le chemin si votre clone n'est pas sous `/home/ubuntu/monitoring-ia`) :
   ```bash
   minikube mount /home/ubuntu/monitoring-ia:/home/ubuntu/monitoring-ia &
   ```
   Laissez ce processus actif pendant que vous utilisez les pipelines ; sans lui, le `hostPath` vu par Minikube ne reflète pas le contenu de l'EC2.

2. Vérifiez à nouveau avec le pod **busybox** + PVC (`ls -la /data`) : `mock_loki_logs.csv` doit être visible.

3. Relancez l'exécution du pipeline depuis l'UI Kubeflow.

*(Voir aussi la section **§3** ci-dessus pour le même principe appliqué au Job d'entraînement `training-job.yaml`.)*
