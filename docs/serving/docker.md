# Conteneurisation du service de Serving (Docker)

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
