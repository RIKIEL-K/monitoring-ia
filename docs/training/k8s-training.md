# Exécution du Batch Job d'entraînement dans Kubernetes

Le but est d'exécuter l'entraînement en batch via Kubernetes, et de logger automatiquement les paramètres, les métriques et le modèle dans MLflow tout en stockant les artefacts dans MinIO.

**Soumettre le Job :**
```bash
kubectl apply -f manifests/training-job.yaml
```

**Suivre les logs :**
```bash
kubectl logs -l app=training -f
```

*(La sortie attendue devrait indiquer la fin de l'entraînement et "Model logged to MLflow")*

!!! warning "Dépannage : Pod bloqué en ContainerCreating (hostPath type check failed)"
    Comme Minikube tourne isolé dans son propre conteneur Docker, le chemin `/home/ubuntu/monitoring-ia` (qui est sur votre EC2) n'existe pas à l'intérieur de Minikube. Il refuse donc de démarrer le pod.
    La solution est de "monter" (partager) ce dossier depuis l'EC2 vers Minikube en utilisant une commande spécifique de Minikube.
    
    Voici les 3 étapes rapides pour corriger cela sur votre EC2 :
    
    **1. Lancer le partage de dossier (en tâche de fond avec le `&` à la fin) :**
    ```bash
    minikube mount /home/ubuntu/monitoring-ia:/home/ubuntu/monitoring-ia &
    ```
    *(Laissez cette commande tourner. Elle vous affichera probablement un message indiquant que le montage est réussi).*
    
    **2. Supprimer le Job bloqué :**
    ```bash
    kubectl delete -f manifests/training-job.yaml
    ```
    
    **3. Relancer le Job proprement :**
    ```bash
    kubectl apply -f manifests/training-job.yaml
    ```
    Cette fois-ci, le pod trouvera bien le dossier contenant vos scripts Python et l'entraînement pourra commencer !
