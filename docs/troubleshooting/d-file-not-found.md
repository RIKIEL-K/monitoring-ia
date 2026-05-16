# D — `FileNotFoundError: /data/...` dans le pipeline

## Symptôme

L'étape `train_model` échoue avec une erreur Python :

```
FileNotFoundError: [Errno 2] No such file or directory: '/data/mock_loki_logs.csv'
```

Dans l'UI Kubeflow, un message du type `Failed to retrieve pod logs` peut masquer la vraie erreur.

## Cause

Le manifeste `manifests/data-pv.yaml` expose les données via un `hostPath` (ex. `/home/ubuntu/monitoring-ia/ML/ml-log-loki/datasets`). Sur une **EC2 avec Minikube**, ce chemin sur le disque de l'EC2 n'est **pas le même** que le système de fichiers **à l'intérieur de la VM Minikube** : le répertoire peut être absent ou **vide** dans le pod, malgré des fichiers présents sur l'hôte Ubuntu.

## Diagnostic

### Étape 1 — Identifier le pod en échec

```bash
kubectl get workflows -n kubeflow
kubectl describe workflow <nom-du-workflow> -n kubeflow | tail -40
kubectl get pods -n kubeflow -l workflows.argoproj.io/workflow=<nom-du-workflow>
```

### Étape 2 — Lire les logs du conteneur Python

```bash
kubectl logs -n kubeflow <nom-du-pod-impl> -c main --tail=-1 | head -80
```

Vous verrez la trace Python complète (`FileNotFoundError`, etc.).

### Étape 3 — Vérifier ce que le PVC expose réellement

Lancer un pod `busybox` avec le PVC monté :

```bash
kubectl run -it --rm pvc-check --restart=Never -n kubeflow \
  --image=busybox \
  --overrides='{"spec":{"containers":[{"name":"c","image":"busybox","stdin":true,"tty":true,"command":["sh"],"volumeMounts":[{"mountPath":"/data","name":"v"}]}],"volumes":[{"name":"v","persistentVolumeClaim":{"claimName":"training-data-pvc"}}]}}' -- sh
```

Dans le shell du pod :

```bash
ls -la /data
head -3 /data/mock_loki_logs.csv
```

- Si `/data` est **vide** alors que les fichiers existent sur l'EC2 → problème de montage Minikube (voir solution ci-dessous)
- Si les fichiers **apparaissent** → le problème est ailleurs (chemin incorrect dans le pipeline)

### Étape 4 — Vérifier le fichier sur l'hôte Ubuntu

```bash
ls -la /home/ubuntu/monitoring-ia/ML/ml-log-loki/datasets/mock_loki_logs.csv
```

## Solution : `minikube mount`

Sur l'EC2, lancer le partage de dossier **en tâche de fond** :

```bash
minikube mount /home/ubuntu/monitoring-ia:/home/ubuntu/monitoring-ia &
```

!!! warning "Laissez ce processus tourner"
    Sans ce processus actif, le `hostPath` vu par Minikube ne reflète pas le contenu de l'EC2. Il doit rester actif pendant toute la durée d'utilisation des pipelines.

Puis vérifier à nouveau avec le pod `busybox` + PVC :

```bash
# Dans le pod busybox
ls -la /data
# mock_loki_logs.csv doit apparaître
```

Finalement, relancer l'exécution du pipeline depuis l'UI Kubeflow.

!!! note "Voir aussi"
    Le même principe s'applique au Job d'entraînement `training-job.yaml` (section Déploiement §3).
