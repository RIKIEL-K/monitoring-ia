
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
> Si le train affiche `[SUCCESS] TRAINING COMPLETE` puis échoue sur l'**upload** d'artefacts vers **`seaweedfs.kubeflow`**, voir **§10.E**.

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

### E. Après « TRAINING COMPLETE » : échec `uploadOutputArtifacts` / `dial tcp ... seaweedfs.kubeflow:9000: i/o timeout`

**Symptôme :** L'entraînement se déroule correctement jusqu'à `[SUCCESS] TRAINING COMPLETE` (MLflow + MinIO OK), puis le **launcher KFP v2** (`launcher_v2.go`) tente d'uploader les `executor-logs` vers un bucket S3 interne et échoue systématiquement :

```
W launcher_v2.go:845] Failed to upload output artifacts: ...
  Put "http://seaweedfs.kubeflow:9000/mlpipeline/v2/artifacts/.../executor-logs-0": 
  dial tcp 10.x.x.x:9000: i/o timeout
E launcher_v2.go:867] All upload artifact attempts failed: ...
F main.go:58] failed to execute component: ...
Error: exit status 1
```

Le pipeline est donc marqué en **erreur** malgré un entraînement réussi. Les artefacts MLflow et les données MinIO (pour MLflow) sont bien présents ; c'est uniquement l'upload des **métadonnées internes de Kubeflow** qui échoue.

---

#### Cause racine

Il y a **deux problèmes combinés** dans la configuration du cluster :

| # | Problème | Détail |
|---|---|---|
| **1** | Le KFP v2 Launcher cherche **`seaweedfs.kubeflow:9000`** | Ce service n'existe pas dans le cluster → `i/o timeout` |
| **2** | Le `workflow-controller-configmap` pointe sur **`minio-service.kubeflow:9000`** | MinIO est dans le namespace `default`, pas `kubeflow` → résolution DNS cassée |

Le **launcher KFP v2** (binaire Go `launcher_v2.go`) lit l'endpoint du dépôt d'artefacts depuis le `workflow-controller-configmap` dans le namespace `kubeflow`. Cette configuration est complètement **indépendante** des variables d'environnement du pod Python (`MLFLOW_S3_ENDPOINT_URL`, `AWS_ENDPOINT_URL`). Toute tentative de redirection via `set_env_variable()` dans `pipeline.py` est inefficace sur ce binaire.

> [!IMPORTANT]
> Le `set_env_variable()` du SDK KFP ne contrôle que le **code Python** du composant. Le **binaire Go du Launcher** qui s'exécute en parallèle dans le même pod lit sa configuration S3 exclusivement depuis le **ConfigMap Kubernetes** `workflow-controller-configmap`.

---

#### Diagnostic (sur l'EC2)

```bash
# 1. Vérifier quels ConfigMaps existent dans kubeflow
kubectl get configmap -n kubeflow | grep -E "artifact|minio|seaweed|pipeline|workflow"

# 2. Lire la configuration actuelle du artifact store
kubectl get configmap workflow-controller-configmap -n kubeflow -o yaml

# 3. Vérifier que le service seaweedfs n'existe pas (attendu : NotFound)
kubectl get svc seaweedfs -n kubeflow

# 4. Vérifier si MinIO est dans le bon namespace
kubectl get svc -n default | grep minio
kubectl get svc -n kubeflow | grep minio
```

**Résultat typique révélant le problème :**

```yaml
# workflow-controller-configmap
artifactRepository:
  s3:
    endpoint: "minio-service.kubeflow:9000"  # ← mauvais namespace !
    bucket: "mlpipeline"
```

```bash
# kubectl get svc seaweedfs -n kubeflow
Error from server (NotFound): services "seaweedfs" not found   # ← service inexistant
```

---

#### Fix permanent (vérifié ✅)

Le fix crée **deux alias DNS** sous forme de Services Kubernetes dans le namespace `kubeflow`, qui redirigent les deux endpoints problématiques vers le MinIO fonctionnel (`minio-service.default`). Aucune recompilation du pipeline n'est nécessaire.

Un script prêt à l'emploi est disponible dans le dépôt :

```bash
bash ~/monitoring-ia/scripts/fix_kfp_artifact_store.sh
```

**Ce que fait le script (étape par étape) :**

**Étape 1 — Service alias `seaweedfs` dans `kubeflow`**

```bash
kubectl apply -f - <<EOF
apiVersion: v1
kind: Service
metadata:
  name: seaweedfs
  namespace: kubeflow
spec:
  type: ExternalName
  externalName: minio-service.default.svc.cluster.local
  ports:
  - name: s3
    port: 9000
    targetPort: 9000
EOF
```

→ `seaweedfs.kubeflow:9000` résout désormais vers MinIO (`default` namespace).

**Étape 2 — Service alias `minio-service` dans `kubeflow`**

```bash
kubectl apply -f - <<EOF
apiVersion: v1
kind: Service
metadata:
  name: minio-service
  namespace: kubeflow
spec:
  type: ExternalName
  externalName: minio-service.default.svc.cluster.local
  ports:
  - name: s3
    port: 9000
    targetPort: 9000
EOF
```

→ `minio-service.kubeflow:9000` résout également vers MinIO.

**Étape 3 — Secret credentials dans `kubeflow`**

```bash
kubectl create secret generic mlpipeline-minio-artifact \
  --from-literal=accesskey=minioadmin \
  --from-literal=secretkey=minioadmin \
  -n kubeflow \
  --dry-run=client -o yaml | kubectl apply -f -
```

**Étape 4 — Créer le bucket `mlpipeline` dans MinIO**

```bash
kubectl run mc-fix --rm -it --image=minio/mc --restart=Never -- \
  bash -c "
    mc alias set minio http://minio-service.default.svc.cluster.local:9000 minioadmin minioadmin --api S3v4 && \
    mc mb --ignore-existing minio/mlpipeline && \
    mc ls minio/"
```

**Étape 5 — Redémarrer le workflow-controller**

```bash
kubectl rollout restart deployment workflow-controller -n kubeflow
kubectl rollout status deployment workflow-controller -n kubeflow --timeout=60s
```

**Vérification finale :**

```bash
kubectl get svc -n kubeflow | grep -E "seaweedfs|minio"
# Attendu :
# minio-service   ExternalName   <none>   minio-service.default.svc.cluster.local   9000/TCP   ...
# seaweedfs       ExternalName   <none>   minio-service.default.svc.cluster.local   9000/TCP   ...
```

---

#### Pourquoi ce fix est permanent

Les Services Kubernetes de type `ExternalName` sont des objets persistants dans etcd. Ils survivent aux redémarrages de pods, aux rollouts, et même aux relancements du cluster Minikube (tant que la configuration est réappliquée). Tout pipeline futur qui tentera de contacter `seaweedfs.kubeflow:9000` sera automatiquement redirigé vers MinIO sans aucune modification du code Python.

```
Avant le fix :
  launcher_v2.go → seaweedfs.kubeflow:9000 → ❌ NXDOMAIN / i/o timeout

Après le fix :
  launcher_v2.go → seaweedfs.kubeflow:9000
                        ↓ (ExternalName DNS)
                   minio-service.default.svc.cluster.local:9000 → ✅ MinIO
```

> [!NOTE]
> Les avertissements `pip` sur les dépendances `kfp` manquantes et le warning **Python 3.7 end-of-life** dans les logs du conteneur sont sans relation avec ce timeout. Ce sont des messages cosmétiques de l'image d'exécution KFP.

---

### F. Étape `deploy-model` : erreurs `403 Forbidden` puis `404 Not Found` — RBAC + Deployment inexistant (vérifié ✅)

Cette étape a nécessité **deux corrections successives** avant de fonctionner. Les voici documentées dans l'ordre.

---

#### F.1 — Erreur `403 Forbidden` : RBAC manquant

**Symptôme :**

```
kubernetes.client.exceptions.ApiException: (403)
Reason: Forbidden
message: "deployments.apps \"log-clustering-serving\" is forbidden:
  User \"system:serviceaccount:kubeflow:pipeline-runner\"
  cannot get resource \"deployments\" in API group \"apps\"
  in the namespace \"default\""
```

**Cause :** Le composant `deploy_model` s'exécute avec l'identité du ServiceAccount `pipeline-runner` (namespace `kubeflow`). Ce SA n'a par défaut **aucun droit** sur les ressources du namespace `default`. Kubernetes refuse toute lecture ou écriture sur les Deployments avec HTTP 403.

> [!IMPORTANT]
> Ce n'est pas un bug du code Python — c'est une restriction **RBAC** de Kubernetes. Le fix se fait **une seule fois** au niveau du cluster.

**Fix — appliquer le manifeste RBAC :**

```bash
kubectl apply -f manifests/pipeline-runner-deploy-rbac.yaml
```

Contenu du manifeste (`manifests/pipeline-runner-deploy-rbac.yaml`) :

```yaml
# Role : droits sur les Deployments dans "default"
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: pipeline-runner-deployer
  namespace: default
rules:
- apiGroups: ["apps"]
  resources: ["deployments"]
  verbs: ["get", "list", "create", "patch", "update"]   # "create" requis pour l'upsert (§F.2)

---

# RoleBinding : lie pipeline-runner (kubeflow) au Role ci-dessus
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: pipeline-runner-deployer-binding
  namespace: default
subjects:
- kind: ServiceAccount
  name: pipeline-runner
  namespace: kubeflow
roleRef:
  kind: Role
  name: pipeline-runner-deployer
  apiGroup: rbac.authorization.k8s.io
```

**Vérification des droits :**

```bash
kubectl get role,rolebinding -n default | grep pipeline-runner

kubectl auth can-i get deployments \
  --as=system:serviceaccount:kubeflow:pipeline-runner -n default
# → yes ✅

kubectl auth can-i create deployments \
  --as=system:serviceaccount:kubeflow:pipeline-runner -n default
# → yes ✅
```

---

#### F.2 — Erreur `404 Not Found` : Deployment inexistant + pattern Upsert

**Symptôme** (après correction du RBAC) :

```
kubernetes.client.exceptions.ApiException: (404)
Reason: Not Found
message: "deployments.apps \"log-clustering-serving\" not found"
```

**Cause :** Le code original faisait un `read_namespaced_deployment()` puis un `patch_namespaced_deployment()`. Si le Deployment `log-clustering-serving` n'a jamais été créé dans le namespace `default`, la lecture retourne 404 et le composant plante — même avec les bons droits RBAC.

**Fix — pattern Upsert dans `deploy_model.py` :**

Le composant a été réécrit pour gérer les deux cas (création + mise à jour) en un seul chemin de code :

```python
try:
    dep = apps_v1.read_namespaced_deployment(deployment_name, deployment_namespace)

    # CAS 1 : Deployment existant → patch de l'image uniquement (rolling update)
    idx = next((i for i, c in enumerate(dep.spec.template.spec.containers)
                if c.name == container_name), None)
    patch = [{"op": "replace",
              "path": f"/spec/template/spec/containers/{idx}/image",
              "value": new_image}]
    apps_v1.patch_namespaced_deployment(
        name=deployment_name, namespace=deployment_namespace,
        body=patch, content_type="application/json-patch+json",
    )
    action = "patché (rolling update déclenché)"

except ApiException as e:
    if e.status != 404:
        raise  # 403, 500... → on propage

    # CAS 2 : Deployment absent → création complète avec toutes les env vars
    apps_v1.create_namespaced_deployment(
        namespace=deployment_namespace,
        body=client.V1Deployment(...)   # spec complète : image, ports, env MLflow/MinIO
    )
    action = "créé (premier déploiement)"
```

---

#### Résumé des deux corrections et ordre d'application

| Ordre | Erreur | Cause | Fix |
|---|---|---|---|
| **1** | `403 Forbidden` | SA `pipeline-runner` sans droits sur `deployments/default` | `kubectl apply -f manifests/pipeline-runner-deploy-rbac.yaml` |
| **2** | `404 Not Found` | Deployment `log-clustering-serving` inexistant | Pattern Upsert dans `deploy_model.py` (crée ou patche) |

```
Flux de décision du composant deploy_model (après fix) :

  read_namespaced_deployment()
        │
        ├── 200 OK  → Deployment existant
        │            → patch image uniquement (rolling update) ✅
        │
        └── 404     → Deployment absent
                     → create_namespaced_deployment() (spec complète) ✅

  Toute autre erreur (403, 500...) → propagée normalement
```

> [!NOTE]
> Les deux fixes sont **permanents** : le Role/RoleBinding RBAC persiste dans etcd, et le code upsert de `deploy_model.py` est versionné dans le dépôt. Le pipeline fonctionne désormais quel que soit l'état initial du cluster — premier déploiement ou mise à jour.

---

### G. Impossible de créer un Run dans l'UI Kubeflow — MySQL : charset, collation et utilisateur (vérifié ✅)

**Symptôme :** L'interface Kubeflow affiche une erreur lors de la création d'un Run, ou les runs restent bloqués sans progresser. Les logs de `ml-pipeline` montrent des erreurs MySQL liées à l'encodage ou à l'authentification.

**Cause :** Trois problèmes MySQL combinés empêchent Kubeflow Pipelines de fonctionner correctement :

| # | Problème | Impact |
|---|---|---|
| **1** | Base `mlpipeline` en charset `utf8mb3` au lieu de `utf8mb4` | Crash sur les caractères spéciaux (émojis, noms de paramètres) |
| **2** | Tables `runs` / `pipelines` non converties en `utf8mb4` | Erreur 3988 ou 1366 lors de l'insertion |
| **3** | Utilisateur `kubeflow` absent ou avec mauvais plugin d'auth | Connexion refusée par `ml-pipeline` |

> [!IMPORTANT]
> Ces trois corrections doivent être appliquées **ensemble et dans l'ordre**. Un oubli suffit à maintenir le bug.

---

#### Fix complet — Procédure pas à pas (vérifié ✅)

**Étape 1 — Se connecter à MySQL**

```bash
kubectl exec -it deploy/mysql -n kubeflow -- mysql -uroot -p
```

**Étape 2 — Créer la base (si nécessaire)**

```sql
CREATE DATABASE IF NOT EXISTS mlpipeline;
```

**Étape 3 — Fix charset UTF-8 (critique)**

```sql
ALTER DATABASE mlpipeline
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
```

**Étape 4 — Convertir les tables principales**

```sql
ALTER TABLE mlpipeline.runs
  CONVERT TO CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

ALTER TABLE mlpipeline.pipelines
  CONVERT TO CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
```

**Étape 5 — Créer l'utilisateur Kubeflow (si absent)**

```sql
CREATE USER 'kubeflow'@'%'
  IDENTIFIED WITH mysql_native_password
  BY 'kubeflow';
```

**Étape 6 — Donner les droits**

```sql
GRANT ALL PRIVILEGES ON mlpipeline.* TO 'kubeflow'@'%';
```

**Étape 7 — Appliquer les changements**

```sql
FLUSH PRIVILEGES;
```

**Étape 8 — Vérification de l'utilisateur**

```sql
SELECT user, host, plugin
FROM mysql.user
WHERE user='kubeflow';
```

Résultat attendu :

```
+---------+------+-----------------------+
| user    | host | plugin                |
+---------+------+-----------------------+
| kubeflow| %    | mysql_native_password |
+---------+------+-----------------------+
```

**Étape 9 — (Optionnel) Vérifier le charset du serveur**

```sql
SHOW VARIABLES LIKE 'character_set%';
```

Les valeurs `character_set_database` et `character_set_server` doivent afficher `utf8mb4`.

**Étape 10 — Redémarrer Kubeflow après le fix**

```bash
kubectl rollout restart deployment ml-pipeline -n kubeflow
kubectl rollout restart deployment metadata-grpc-deployment -n kubeflow
```

---

#### Vérification finale

Dans l'UI Kubeflow → **Pipelines** → **Create Run** :

- Le run doit passer successivement par les états : `CREATED` → `RUNNING` → `SUCCESS`

---

#### Résumé des 3 conditions à valider

```
Pour que Kubeflow Pipelines fonctionne, ces 3 conditions doivent être remplies :

  1. Base mlpipeline
     ✓ CHARACTER SET = utf8mb4
     ✓ Tables runs + pipelines converties

  2. Utilisateur MySQL
     ✓ kubeflow@%
     ✓ plugin = mysql_native_password

  3. Permissions
     ✓ ALL PRIVILEGES ON mlpipeline.*
```

> [!TIP]
> Si les tables `runs` ou `pipelines` n'existent pas encore au moment du fix (premier démarrage de Kubeflow), l'étape 4 peut être ignorée — les tables seront créées directement avec le bon charset. Relancez l'étape 4 après le premier démarrage de `ml-pipeline` si des erreurs de collation persistent.
