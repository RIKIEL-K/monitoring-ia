# Détection d'Anomalies avec IsolationForest

L'algorithme **IsolationForest** est utilisé pour détecter des comportements anormaux au niveau des métriques collectées par **Prometheus**.

## Scripts et Fichiers

Les scripts Python associés sont situés dans `ML/` (ou `ML/ML_Prometheus/ML_detect_metrics/`) :

- `train_model.py` : Script d'entraînement du modèle de détection d'anomalies.
- `detect_anomalie.py` : Script utilisé pour l'inférence afin de détecter les anomalies en temps réel.

## Exécution

```bash
cd ~/monitoring-ia/ML
python3 train_model.py
python3 detect_anomalie.py
```

## Logs d'exécution

Les journaux sont stockés dans `/var/log/ml/`.
Vous pouvez les consulter pour analyser les résultats de l'apprentissage et de la détection :

```bash
tail -20 /var/log/ml/train.log
tail -20 /var/log/ml/detect.log

# Suivre en temps réel (Ctrl+C pour arrêter)
tail -f /var/log/ml/detect.log
```
