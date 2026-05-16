# Déploiement Kubeflow Pipelines

Kubeflow Pipelines (KFP) permet d'orchestrer, déployer et gérer des workflows de Machine Learning.

## Données d'entraînement — Préparer le PVC

```bash
# Placer le dataset dans /root/code/data/
# Puis déployer le PV et PVC
kubectl apply -f manifests/data-pv.yaml
```

## Déploiement via le script global

```bash
chmod +x deploy_stack.sh
./deploy_stack.sh
```

Le script déploie MinIO, crée les buckets, déploie MLflow, puis installe Kubeflow. L'attente peut prendre de 5 à 10 minutes.

## Accès à l'UI Kubeflow

L'interface est exposée sur le port `30502`.

```bash
# Depuis une EC2 distante, ouvrir un tunnel SSH
ssh -i "C:\chemin\vers\votre_cle.pem" \
  -L 30502:127.0.0.1:30502 \
  ubuntu@<IP_PUBLIQUE_DE_VOTRE_EC2>
```

Accédez ensuite à : `http://localhost:30502`

## Tester l'intégration Kubeflow ↔ MLflow

```bash
kubectl apply -f manifests/kubeflow/mlflow-integration-check.yaml
```

Suivez l'exécution directement dans l'UI Kubeflow.

## Problèmes courants au déploiement

| Problème | Solution |
|---|---|
| Pod bloqué `Init:CreateContainerConfigError` | [Troubleshooting A](../troubleshooting/a-container-config-error.md) |
| Run impossible à créer | [Troubleshooting G](../troubleshooting/g-mysql-charset.md) |
| Timeout artefacts après entraînement | [Troubleshooting E](../troubleshooting/e-seaweedfs-timeout.md) |
