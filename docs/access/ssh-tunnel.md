# Accès distant via Tunnel SSH

Pour accéder aux interfaces web (MinIO, MLflow, Kubeflow) depuis votre navigateur local alors que la stack tourne sur une EC2 distante, la méthode la plus fiable est le **tunnel SSH**.

## Étape 1 — Sur votre instance EC2

Relayer les ports du cluster K8s vers le `localhost` de l'EC2 :

```bash
kubectl port-forward --address 127.0.0.1 svc/minio-service 30901:9001 &
kubectl port-forward --address 127.0.0.1 svc/mlflow-service 30500:5000 &
```

## Étape 2 — Sur votre machine locale (Windows)

Ouvrez un terminal PowerShell et connectez-vous avec la commande suivante :

```bash
ssh -i "C:\chemin\vers\votre_cle.pem" \
  -L 30901:127.0.0.1:30901 \
  -L 30500:127.0.0.1:30500 \
  -L 30502:127.0.0.1:30502 \
  ubuntu@<IP_PUBLIQUE_DE_VOTRE_EC2>
```

Remplacez :
- `C:\chemin\vers\votre_cle.pem` par le chemin de votre clé SSH
- `<IP_PUBLIQUE_DE_VOTRE_EC2>` par l'adresse IP publique de votre instance

## Étape 3 — Dans votre navigateur

Tant que la fenêtre SSH reste ouverte, votre tunnel fonctionne. Accédez aux UIs :

| Service | URL locale |
|---|---|
| MinIO UI | [http://localhost:30901](http://localhost:30901) |
| MLflow | [http://localhost:30500](http://localhost:30500) |
| Kubeflow | [http://localhost:30502](http://localhost:30502) |

!!! warning "Gardez la fenêtre SSH ouverte"
    Si vous fermez le terminal SSH, le tunnel est coupé et les UIs deviennent inaccessibles.

## Ajouter d'autres ports

Pour ajouter le port de l'API de serving (`30501`) :

```bash
ssh -i "C:\chemin\vers\votre_cle.pem" \
  -L 30901:127.0.0.1:30901 \
  -L 30500:127.0.0.1:30500 \
  -L 30502:127.0.0.1:30502 \
  -L 30501:127.0.0.1:30501 \
  ubuntu@<IP_PUBLIQUE_DE_VOTRE_EC2>
```
