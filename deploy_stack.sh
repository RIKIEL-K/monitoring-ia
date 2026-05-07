#!/bin/bash
set -e
echo ""
echo "====================================================="
echo "Starting installation of MinIO, MLflow, and Kubeflow"
echo "====================================================="
echo ""

########################################
# MinIO Setup
########################################
echo "Deploying MinIO..."
# Utilisation du chemin relatif (adapté par rapport à /root/.minio-deployment.yaml)
kubectl apply --validate=false -f manifests/minio-deployment.yaml
kubectl apply --validate=false -f manifests/minio-service.yaml

echo "Waiting for MinIO pod to become Ready..."
kubectl wait --for=condition=Ready pod -l app=minio --timeout=180s
MINIO_POD=$(kubectl get pods -l app=minio -o jsonpath='{.items[0].metadata.name}')
echo "MinIO pod is ready: $MINIO_POD"

echo "Creating 'mlartifacts' bucket in MinIO..."
MINIO_NODE_IP=$(minikube ip)
mc alias set local http://${MINIO_NODE_IP}:30900 minioadmin minioadmin >/dev/null 2>&1
mc mb local/mlartifacts || true
echo "Bucket 'mlartifacts' verified/created."
echo ""

########################################
# MLflow Setup
########################################
echo "Deploying MLflow..."
# Utilisation du chemin relatif
kubectl apply --validate=false -f manifests/mlflow-deployment.yaml
kubectl apply --validate=false -f manifests/mlflow-service.yaml

echo "Waiting for MLflow pod to be created..."
sleep 5 # initial delay to allow pod to appear
MLFLOW_POD=""
until [[ -n "$MLFLOW_POD" ]]; do
  echo " ...waiting for MLflow pod to be created"
  sleep 3
  MLFLOW_POD=$(kubectl get pods -l app=mlflow -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
done

echo "Waiting for MLflow pod to become Ready..."
kubectl wait --for=condition=Ready pod/"$MLFLOW_POD" --timeout=180s
echo "MLflow pod is ready: $MLFLOW_POD"
echo ""

########################################
# Kubeflow Pipelines Setup
########################################
echo "Installing Kubeflow Pipelines..."
export PIPELINE_VERSION=2.15.0
kubectl apply -k "github.com/kubeflow/pipelines/manifests/kustomize/cluster-scoped-resources?ref=$PIPELINE_VERSION"
kubectl wait --for condition=established --timeout=60s crd/applications.app.k8s.io
kubectl apply -k "github.com/kubeflow/pipelines/manifests/kustomize/env/dev?ref=$PIPELINE_VERSION"

# 💡 Troubleshooting : si des pods (proxy-agent, workflow-controller) crashent en boucle,
# utiliser platform-agnostic à la place (vérifié sur Minikube v2.0.0+, cf. kubeflow/pipelines#9546) :
#   kubectl apply -k "github.com/kubeflow/pipelines/manifests/kustomize/env/platform-agnostic?ref=$PIPELINE_VERSION"

echo "Waiting for Kubeflow Pipeline pods to become Ready (this may take several minutes)..."
kubectl wait pods -l application-crd-id=kubeflow-pipelines -n kubeflow --for condition=Ready --timeout=600s || echo "Certains pods prennent plus de temps..."

echo "Applying UI NodePort patch..."
kubectl apply --validate=false -f manifests/kubeflow/kfp-ui-nodeport-patch.yaml

echo ""
echo "====================================="
echo "Installation completed successfully."
echo "====================================="
echo ""
