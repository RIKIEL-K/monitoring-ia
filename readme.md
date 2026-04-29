# IsolationForest
cd ~/monitoring-ia/ML
python3 train_model.py
python3 detect_anomalie.py

# Prophet
cd ~/monitoring-ia/ML/ML_Prophet
python3 train_forcasting_model.py
python3 forecast_metrics.py


# Dernières lignes
tail -20 /var/log/ml/train.log
tail -20 /var/log/ml/detect.log
tail -20 /var/log/ml/train_prophet.log
tail -20 /var/log/ml/forecast.log

# Suivre en temps réel (Ctrl+C pour arrêter)
tail -f /var/log/ml/detect.log

# Vérifier que le cron tourne
crontab -l
grep CRON /var/log/syslog | tail -10

ls -lh ~/monitoring-ia/ML/models/
ls -lh ~/monitoring-ia/ML/models/prophet/
