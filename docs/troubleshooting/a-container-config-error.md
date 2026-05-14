# A — `Init:CreateContainerConfigError` (runAsNonRoot)

## Symptôme

Le pipeline Kubeflow ne démarre pas. La commande `kubectl describe pod <pod-name> -n kubeflow` affiche :

```
Error: container has runAsNonRoot and image will run as root
```

Le pod reste bloqué avec le statut `Init:CreateContainerConfigError`.

## Cause

Kubernetes bloque le conteneur interne d'Argo (`argoexec`) car il tente de se lancer avec les droits **root**, ce qui viole la politique de sécurité de Kubeflow.

## Solution

Forcer l'exécuteur Argo à utiliser un utilisateur standard (`8737`) via le `workflow-controller-configmap` :

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

## Vérification

```bash
kubectl get pods -n kubeflow -l app=workflow-controller
# Le pod doit passer en Running
```

!!! note "Note sur containerRuntimeExecutor"
    Si vous aviez configuré `containerRuntimeExecutor: emissary` manuellement, **supprimez-le** car il n'est plus supporté dans les versions récentes d'Argo (v3.4+).
