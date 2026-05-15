# Monitoring IA

Bienvenue dans le repository de **Monitoring IA**.
Ce projet fournit une suite d'outils basés sur le Machine Learning pour la détection d'anomalies, le forecasting et le clustering de logs, en s'appuyant sur Prometheus et Loki.

> [!IMPORTANT]
> L'ensemble de la documentation détaillée (paramètres avancés, cycle de vie MLflow, et tests End-to-End sur EC2) a été migrée vers notre site **MkDocs**.
> 
> **👉 Consultez la documentation complète en générant le site localement (`mkdocs serve`) ou via le déploiement de la doc.**

---

## 🚀 Quickstart

### Détection d'Anomalies (IsolationForest)
Surveille les métriques Prometheus.
```bash
cd ~/monitoring-ia/ML
python3 train_model.py
python3 detect_anomalie.py
```

### Prévision / Forecasting (Prophet)
Prédit les tendances futures des métriques Prometheus.
```bash
cd ~/monitoring-ia/ML/ML_Prophet
python3 train_forcasting_model.py
python3 forecast_metrics.py
```

### Logs & Vérifications

Consulter les logs récents de l'exécution :
```bash
tail -20 /var/log/ml/train.log
tail -20 /var/log/ml/detect.log
tail -20 /var/log/ml/train_prophet.log
tail -20 /var/log/ml/forecast.log

# Suivre en temps réel (Ctrl+C pour arrêter)
tail -f /var/log/ml/detect.log
```

Vérifier que les tâches planifiées s'exécutent (Cron) :
```bash
crontab -l
grep CRON /var/log/syslog | tail -10
```

Vérifier les modèles générés :
```bash
ls -lh ~/monitoring-ia/ML/models/
ls -lh ~/monitoring-ia/ML/models/prophet/
```

### Clustering de Logs (Loki) & MLOps
Pour exécuter le script de log clustering avec MLflow et MinIO (actuellement sur EC2) :
```bash
python scripts/train_log_clustering.py --register-model --promote-to-production
```
*(Pour tous les arguments `argparse` disponibles et le processus de tracking MLflow complet, consultez la documentation **MkDocs** dans `docs/`).*
