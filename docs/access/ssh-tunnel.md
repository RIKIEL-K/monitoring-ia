# Accès distant via Tunnel SSH

Pour accéder aux interfaces web (MinIO, MLflow, Kubeflow) depuis votre navigateur local alors que la stack tourne sur une EC2 (Utiliser une EC2 c5a.4xlargesur aws ) distante, la méthode la plus fiable est le **tunnel SSH**.

## Étape 1 : Sur votre instance EC2

Relayer les ports du cluster Kubeflow k8s vers le `localhost` de l'EC2 :

```bash
nohup kubectl port-forward --address 127.0.0.1 -n kubeflow svc/ml-pipeline-ui 8080:80 > kfp.log 2>&1 &

nohup kubectl port-forward --address 127.0.0.1 -n default svc/mlflow-service 5000:5000 > mlflow.log 2>&1 &

nohup kubectl port-forward --address 127.0.0.1 -n default svc/minio-service 9000:9000 9001:9001 > minio.log 2>&1 &
```

## Étape 2 : Sur votre machine locale (Windows)

Ouvrez un terminal PowerShell et connectez-vous avec la commande suivante :

```bash
ssh -i "C:\chemin\vers\votre_cle.pem" -L 8080:127.0.0.1:8080 -L 5000:127.0.0.1:5000 -L 9000:127.0.0.1:9000 -L 9001:127.0.0.1:9001 ubuntu@<IP_PUBLIQUE_DE_VOTRE_EC2>
```

Remplacez :
- `C:\chemin\vers\votre_cle.pem` par le chemin de votre clé SSH
- `<IP_PUBLIQUE_DE_VOTRE_EC2>` par l'adresse IP publique de votre instance

## Étape 3 : Dans votre navigateur

Tant que la fenêtre SSH reste ouverte, votre tunnel fonctionne. Accédez aux UIs :

| Service | URL locale |
|---|---|
| MinIO UI | [http://localhost:30901](http://localhost:30901) |
| MLflow | [http://localhost:30500](http://localhost:30500) |
| Kubeflow | [http://localhost:30502](http://localhost:30502) |

!!! warning "Gardez la fenêtre SSH ouverte"
    Si vous fermez le terminal SSH, le tunnel est coupé et les UIs deviennent inaccessibles.
