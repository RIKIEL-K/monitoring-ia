# Accès distant aux UIs (Tunnel SSH)

Pour afficher les interfaces web (MinIO et MLflow) sur votre navigateur Chrome en local alors que tout tourne sur une machine EC2 distante, la méthode la plus fiable et la plus sécurisée (sans avoir à modifier les pare-feux d'AWS) est de créer un Tunnel SSH.

Voici les 2 étapes simples à suivre :

**Étape 1 : Sur votre instance EC2**
Vous devez d'abord relayer les ports du cluster K8s vers le réseau local (localhost) de votre instance EC2. Tapez ces deux commandes (elles s'exécuteront en arrière-plan) :

```bash
kubectl port-forward --address 127.0.0.1 svc/minio-service 30901:9001 &
kubectl port-forward --address 127.0.0.1 svc/mlflow-service 30500:5000 &
```

**Étape 2 : Sur votre machine locale (Windows/Mac/Linux)**
Ouvrez un nouveau terminal sur votre propre ordinateur et connectez-vous à votre EC2 avec cette commande spéciale qui va lier les ports de l'EC2 à ceux de votre PC :

```bash
ssh -i "C:\chemin\vers\votre_cle.pem" -L 30901:127.0.0.1:30901 -L 30500:127.0.0.1:30500 ubuntu@<IP_PUBLIQUE_DE_VOTRE_EC2>
```
*(Remplacez le chemin de la clé .pem et `<IP_PUBLIQUE_DE_VOTRE_EC2>` par vos vraies valeurs).*

**Étape 3 : Sur votre navigateur Chrome**
Tant que la fenêtre SSH de l'Étape 2 reste ouverte, votre tunnel fonctionne ! Ouvrez simplement Chrome sur votre ordinateur et allez sur :

- **MinIO** : http://localhost:30901
- **MLflow** : http://localhost:30500
