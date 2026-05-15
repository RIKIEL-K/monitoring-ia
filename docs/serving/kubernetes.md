# Déploiement de l'API de Prédiction (Serving)

Une fois l'image construite, déployez le `Deployment` et le `Service` NodePort dans Kubernetes :

```bash
kubectl apply -f manifests/model-deployment.yaml
kubectl apply -f manifests/model-service.yaml
```

**Suivre le démarrage des pods :**
```bash
kubectl get pods -l app=model-serving -w
```
*(Attendez que les pods passent en statut `Running` avec `READY 1/1`. Le démarrage peut prendre environ 30 secondes le temps que le modèle soit téléchargé depuis MinIO).*

## Tests de l'API

Une fois les pods prêts, vous pouvez tester l'API qui est exposée sur le port `30501` par le Service NodePort.

**Vérifier la santé de l'API :**
```bash
curl http://localhost:30501/ping
```
*(Attendu: 200 OK ou réponse vide, cela prouve que le modèle est bien chargé en mémoire).*

**Tester une prédiction :**
```bash
# Exemple avec des logs textuels
curl -X POST http://localhost:30501/invocations \
-H "Content-Type: application/json" \
-d '{
  "dataframe_split": {
    "columns": ["message"],
    "data": [
      ["level=error msg=\"timeout connection to database\""],
      ["level=info user=admin action=login success=true"]
    ]
  }
}'
```
*(Attendu : un JSON contenant le cluster associé à chaque ligne de log).*
