# E — Timeout SeaweedFS / Artefacts KFP (`i/o timeout`)

## Symptôme

L'entraînement se déroule correctement jusqu'à `[SUCCESS] TRAINING COMPLETE`, puis le **launcher KFP v2** tente d'uploader les `executor-logs` vers un bucket S3 interne et échoue :

```
W launcher_v2.go:845] Failed to upload output artifacts: ...
  Put "http://seaweedfs.kubeflow:9000/mlpipeline/v2/artifacts/.../executor-logs-0":
  dial tcp 10.x.x.x:9000: i/o timeout
E launcher_v2.go:867] All upload artifact attempts failed: ...
F main.go:58] failed to execute component: ...
Error: exit status 1
```

Le pipeline est marqué en **erreur** malgré un entraînement réussi.

## Cause

Deux problèmes combinés dans la configuration du cluster :

| # | Problème | Détail |
|---|---|---|
| **1** | Le KFP v2 Launcher cherche `seaweedfs.kubeflow:9000` | Ce service n'existe pas dans le cluster → `i/o timeout` |
| **2** | Le `workflow-controller-configmap` pointe sur `minio-service.kubeflow:9000` | MinIO est dans le namespace `default`, pas `kubeflow` → résolution DNS cassée |

!!! important "Le `set_env_variable()` est inefficace ici"
    Le launcher KFP v2 (binaire Go `launcher_v2.go`) lit sa configuration S3 **exclusivement** depuis le ConfigMap Kubernetes `workflow-controller-configmap`. Toute tentative de redirection via `set_env_variable()` dans `pipeline.py` est **sans effet** sur ce binaire.

## Diagnostic

```bash
# 1. Vérifier les ConfigMaps existants
kubectl get configmap -n kubeflow | grep -E "artifact|minio|seaweed|pipeline|workflow"

# 2. Lire la configuration actuelle du artifact store
kubectl get configmap workflow-controller-configmap -n kubeflow -o yaml

# 3. Vérifier que seaweedfs n'existe pas (attendu : NotFound)
kubectl get svc seaweedfs -n kubeflow

# 4. Vérifier le namespace de MinIO
kubectl get svc -n default | grep minio
kubectl get svc -n kubeflow | grep minio
```

**Résultat typique révélant le problème :**

```yaml
# workflow-controller-configmap
artifactRepository:
  s3:
    endpoint: "minio-service.kubeflow:9000"  # <- mauvais namespace !
    bucket: "mlpipeline"
```

```
# kubectl get svc seaweedfs -n kubeflow
Error from server (NotFound): services "seaweedfs" not found  # <- service inexistant
```

## Fix — Script automatisé (vérifié)

```bash
bash ~/monitoring-ia/scripts/fix_kfp_artifact_store.sh
```

### Ce que fait le script, étape par étape

**Étape 1 — Alias DNS `seaweedfs` dans `kubeflow`**

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

`seaweedfs.kubeflow:9000` résout désormais vers MinIO.

**Étape 2 — Alias DNS `minio-service` dans `kubeflow`**

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

## Vérification

```bash
kubectl get svc -n kubeflow | grep -E "seaweedfs|minio"
```

Résultat attendu :

```
minio-service   ExternalName   <none>   minio-service.default.svc.cluster.local   9000/TCP   ...
seaweedfs       ExternalName   <none>   minio-service.default.svc.cluster.local   9000/TCP   ...
```

## Pourquoi ce fix est permanent

Les Services de type `ExternalName` sont des objets persistants dans `etcd`. Ils survivent aux redémarrages de pods, aux rollouts et aux relancements de Minikube.

```
Avant le fix :
  launcher_v2.go → seaweedfs.kubeflow:9000 → NXDOMAIN / i/o timeout

Apres le fix :
  launcher_v2.go → seaweedfs.kubeflow:9000
                        ↓ (ExternalName DNS)
                   minio-service.default.svc.cluster.local:9000 → MinIO OK
```

!!! note "Messages pip sans impact"
    Les avertissements `pip` sur les dépendances `kfp` manquantes et le warning Python 3.7 end-of-life dans les logs du conteneur sont **sans relation** avec ce timeout. Ce sont des messages cosmétiques de l'image d'exécution KFP.
