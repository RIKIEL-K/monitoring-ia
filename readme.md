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

# Log Clustering (Loki)
# Le script train_log_clustering.py utilise argparse pour paramétrer le modèle K-Means, TF-IDF et l'intégration MLflow.
#
# Arguments principaux :
# --csv-path               : Chemin vers le dataset CSV des logs Loki (défaut : datasets/mock_loki_logs.csv)
# --output-dir             : Répertoire de sortie pour le CSV résumé (défaut : datasets)
# --max-features           : Nombre max de features TF-IDF (défaut : 100). Limite le vocabulaire, ignore les termes trop rares.
# --min-df                 : Fréquence document minimale TF-IDF (défaut : 2).
# --max-df                 : Fréquence document maximale TF-IDF (défaut : 0.95).
# --n-clusters             : Nombre de clusters pour K-Means (défaut : 5). Définit le nombre de groupes dans lesquels classer les logs.
# --n-init                 : Nombre d'initialisations K-Means (défaut : 10).
# --random-state           : Seed pour garantir la reproductibilité des résultats (défaut : 42).
# --k-range                : Valeurs de k à évaluer via Elbow + Silhouette, séparées par des virgules (défaut : 3,5,8,10,12,15).
# --experiment-name        : Nom de l'expérience dans MLflow (défaut : log-clustering-loki).
# --run-name               : Nom du run dans MLflow (auto-généré si non spécifié).
# --register-model         : (flag) Enregistrer le modèle dans le MLflow Model Registry (stocké sur MinIO).
#                            Le modèle est placé en Staging par défaut.
# --model-name             : Nom du modèle dans le Model Registry (défaut : log-clustering-kmeans).
# --promote-to-production  : (flag) Promouvoir la version vers Production après l'enregistrement en Staging.
#                            Archive automatiquement les versions précédentes en Production.
#
# Cycle de vie du modèle :
#   --register-model seul          → Staging  (validation, tests en cours)
#   --register-model --promote-to-production → Production (modèle validé, prêt pour la prod)
#
# Exemple minimal (tracking uniquement, pas de registry) :
# python scripts/train_log_clustering.py
#
# Enregistrement dans le registry (→ Staging par défaut) :
# python scripts/train_log_clustering.py --register-model
#
# Promotion directe en Production :
# python scripts/train_log_clustering.py --register-model --promote-to-production
#
# Exemple complet :
# python scripts/train_log_clustering.py \
#   --n-clusters 8 \
#   --max-features 150 \
#   --experiment-name "loki-prod" \
#   --register-model \
#   --model-name log-clustering-kmeans \
#   --promote-to-production
# --- Exécution Reproductible (MLflow Project) ---
# Vous pouvez aussi exécuter le projet via son environnement conda isolé :
# mlflow run ML/ML_Log_Loki -P n_clusters=8 -P register_model=true -P promote_to_production=true
#
# ===================================================================
# 🚀 TEST END-TO-END DU WORKFLOW SUR EC2
# ===================================================================
#
# ÉTAPE 1 : Entraîner et promouvoir le modèle en Production
# python3 ML/ML_Log_Loki/scripts/train_log_clustering.py --register-model=true --promote-to-production=true
#
# ÉTAPE 2 : Démarrer le serveur API MLflow (Laissez tourner ou utilisez screen/tmux)
# python3 -m mlflow models serve -m "models:/log-clustering-kmeans/Production" -p 5001 --env-manager local
#
# ÉTAPE 3 : Tester l'API avec de nouveaux logs (dans un autre terminal)
# curl -X POST -H "Content-Type: application/json" -d '{
#   "dataframe_split": {
#     "columns": ["message"],
#     "data": [
#       ["level=error msg=\"timeout connection to database\""],
#       ["level=info user=admin action=login success=true"]
#     ]
#   }
# }' http://localhost:5001/invocations
#
# (La réponse devrait être un JSON contenant le cluster_id et le cluster_label pour chaque log)
