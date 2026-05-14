"""
Log Clustering Pipeline — Validation (quality gate) via MLflow REST.

Lit les métriques du run (notamment anomaly_rate) et refuse le déploiement
si les seuils ne sont pas respectés (RuntimeError → échec du step KFP).
"""

import json

from kfp import dsl


@dsl.component(
    base_image="python:3.9",
    packages_to_install=["requests"]
)
def validate_model(
    mlflow_tracking_uri: str,
    run_id: str,
    anomaly_rate_min: float,
    anomaly_rate_max: float,
) -> str:
    """
    Valide les performances via l'API REST MLflow (GET .../runs/get).

    - Récupère run.data.metrics, construit un dict clé -> valeur float.
    - Métrique attendue : anomaly_rate (fraction 0–1 loguée par train_model).
    - Compare anomaly_rate * 100 aux seuils min/max (exprimés en %).

    Returns:
        JSON string avec decision PASSED / FAILED et détails.

    Raises:
        RuntimeError: si FAILED (bloque le pipeline avant deploy_model).
    """
    import requests

    base = mlflow_tracking_uri.rstrip("/")
    print(f"Validation du run MLflow: {run_id}")
    print(
        f"Plage acceptable pour anomaly_rate (agrégée en %): "
        f"{anomaly_rate_min}% – {anomaly_rate_max}%"
    )

    api_url = f"{base}/api/2.0/mlflow/runs/get"
    response = requests.get(api_url, params={"run_id": run_id}, timeout=60)
    response.raise_for_status()

    run_data = response.json()
    metrics = run_data["run"]["data"]["metrics"]
    metrics_dict = {}
    for m in metrics:
        key = m["key"]
        raw = m["value"]
        metrics_dict[key] = float(raw)

    print(f"Métriques récupérées: {metrics_dict}")

    anomaly_rate = metrics_dict.get("anomaly_rate")
    if anomaly_rate is None:
        validation_result = {
            "decision": "FAILED",
            "reason": "métrique anomaly_rate absente du run",
            "metrics": metrics_dict,
        }
    else:
        anomaly_pct = anomaly_rate * 100.0
        if anomaly_rate_min <= anomaly_pct <= anomaly_rate_max:
            decision = "PASSED"
            reason = (
                f"Taux anomaly_rate {anomaly_pct:.2f}% dans la plage "
                f"[{anomaly_rate_min}%, {anomaly_rate_max}%]"
            )
        else:
            decision = "FAILED"
            reason = (
                f"Taux anomaly_rate {anomaly_pct:.2f}% hors plage "
                f"[{anomaly_rate_min}%, {anomaly_rate_max}%]"
            )
        validation_result = {
            "decision": decision,
            "reason": reason,
            "anomaly_rate": anomaly_pct,
            "threshold_min_pct": anomaly_rate_min,
            "threshold_max_pct": anomaly_rate_max,
            "metrics": metrics_dict,
        }

    out = json.dumps(validation_result, ensure_ascii=False)
    print(f"Résultat validation: {validation_result['decision']}")
    print(f"Détail: {validation_result.get('reason', '')}")

    if validation_result["decision"] != "PASSED":
        raise RuntimeError(out)

    return out
