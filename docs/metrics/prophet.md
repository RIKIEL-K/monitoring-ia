# Prévision (Forecasting) avec Prophet

Le modèle **Prophet** (développé par Meta) est utilisé pour effectuer des prévisions temporelles (forecasting) sur les métriques issues de **Prometheus**. Cela permet d'anticiper l'évolution de la consommation des ressources et de planifier la scalabilité de l'infrastructure.

## Scripts et Fichiers

Les scripts Python sont habituellement situés dans `ML/ML_Prophet` (ou `ML/ML_Prometheus/ML_Forecasting_Prophet/`) :

- `train_forcasting_model.py` : Script pour entraîner le modèle prédictif sur l'historique des métriques.
- `forecast_metrics.py` : Script permettant de générer les prévisions futures.

## Exécution

```bash
cd ~/monitoring-ia/ML/ML_Prophet
python3 train_forcasting_model.py
python3 forecast_metrics.py
```

## Logs d'exécution

Les journaux sont stockés dans `/var/log/ml/`.
Vous pouvez vérifier l'avancement via les commandes suivantes :

```bash
tail -20 /var/log/ml/train_prophet.log
tail -20 /var/log/ml/forecast.log
```
