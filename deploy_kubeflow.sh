#!/bin/bash
set -e

echo "================================================================"
echo "          Déploiement de Kubeflow Pipelines (KFP)"
echo "================================================================"

# Définir la version
export PIPELINE_VERSION=2.14.4
echo "Version de KFP : $PIPELINE_VERSION"

echo ""
echo "1. Application des ressources cluster-scoped (CRDs)..."
kubectl apply -k "github.com/kubeflow/pipelines/manifests/kustomize/cluster-scoped-resources?ref=$PIPELINE_VERSION"

echo ""
echo "2. Attente de l'établissement des CRDs (applications.app.k8s.io)..."
kubectl wait --for condition=established --timeout=60s crd/applications.app.k8s.io

echo ""
echo "3. Application des manifestes spécifiques à l'environnement (platform-agnostic)..."
kubectl apply -k "github.com/kubeflow/pipelines/manifests/kustomize/env/platform-agnostic?ref=$PIPELINE_VERSION"

echo ""
echo "4. Attente que les pods Kubeflow soient prêts (cela peut prendre 5-10 minutes)..."
# Ne pas échouer le script si le wait timeout
kubectl wait pods -l application-crd-id=kubeflow-pipelines -n kubeflow --for condition=Ready --timeout=600s || echo "Certains pods prennent plus de temps à démarrer. Vous pouvez vérifier avec 'kubectl get pods -n kubeflow'."

echo ""
echo "5. Application du patch NodePort pour exposer l'UI de Kubeflow sur le port 30502..."
# Assuming the user runs this script from the project root where manifests/kubeflow exists
kubectl apply -f manifests/kubeflow/kfp-ui-nodeport-patch.yaml

echo ""
echo "6. Vérification des services dans le namespace kubeflow..."
kubectl get svc -n kubeflow

echo ""
echo "================================================================"
echo "          Kubeflow Pipelines a été déployé avec succès !"
echo "================================================================"
echo "L'interface utilisateur de Kubeflow (UI) est exposée sur le NodePort 30502."
echo "Pour y accéder depuis votre machine locale, vous pouvez utiliser un tunnel SSH :"
echo "  ssh -i <votre-cle.pem> -L 30502:127.0.0.1:30502 ubuntu@<VOTRE-IP-EC2>"
echo "Puis ouvrez http://localhost:30502 dans votre navigateur."
echo ""
echo "Pour tester l'intégration avec MLflow, vous pouvez soumettre le workflow Argo :"
echo "  kubectl apply -f manifests/kubeflow/mlflow-integration-check.yaml"
echo "================================================================"
