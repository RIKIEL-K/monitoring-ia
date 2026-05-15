# Documentation de Monitoring IA

Bienvenue dans la documentation du projet **Monitoring IA**.

Ce projet a pour objectif de surveiller une infrastructure en s'appuyant sur l'intelligence artificielle pour l'analyse des logs (via Loki) et l'analyse des métriques (via Prometheus).

## Composants Principaux

- **Analyse des Métriques (Prometheus)** :
    - Utilisation d'**IsolationForest** pour la détection d'anomalies en temps réel.
    - Utilisation de **Prophet** pour la prévision (forecasting) des métriques futures.
- **Analyse des Logs (Loki)** :
    - Classification et **Clustering** des logs avec K-Means et TF-IDF.
- **Déploiement et MLOps** :
    - Suivi des expérimentations, des métriques de modèles et de leur cycle de vie via **MLflow**.
    - Stockage persistant des artefacts avec **MinIO**.
    - Le tout orchestré et testé sur des environnements Cloud (**AWS EC2**).

Utilisez le menu de navigation pour accéder aux détails techniques, aux procédures de déploiement et aux arguments de configuration des différents modèles.
