"""
Log Clustering Pipeline — Kubeflow Training Component

Composant KFP qui entraîne un pipeline TF-IDF + K-Means sur les logs Loki.
Intègre MLflow pour le tracking des expériences et MinIO comme artifact store S3.

Ce fichier est conçu pour être compilé et exécuté par Kubeflow Pipelines.
"""

from kfp import dsl


@dsl.component(
    base_image="python:3.9",
    packages_to_install=[
        "mlflow",
        "scikit-learn",
        "pandas",
        "boto3",
        "numpy",
        "opentelemetry-api==1.24.0",
        "opentelemetry-sdk==1.24.0",
        "opentelemetry-exporter-otlp==1.24.0",
    ]
)
def train_model(
    # MLflow configuration
    mlflow_tracking_uri: str,
    minio_endpoint: str,
    aws_access_key: str,
    aws_secret_key: str,
    experiment_name: str,
    # Data configuration
    data_path: str,
    # TF-IDF hyperparameters
    max_features: int,
    min_df: int,
    max_df: float,
    # K-Means hyperparameters
    n_clusters: int,
    n_init: int,
    random_state: int,
    # Evaluation
    k_range: str,
    # Model naming
    model_name: str,
) -> str:
    """
    Train a TF-IDF + K-Means log clustering pipeline.

    Loads Loki log data, cleans messages, extracts patterns,
    vectorizes with TF-IDF, clusters with K-Means, labels clusters,
    and logs everything to MLflow (params, metrics, PyFunc model).

    Args:
        mlflow_tracking_uri: MLflow tracking server URL
        minio_endpoint: MinIO S3 endpoint for artifact storage
        aws_access_key: MinIO access key
        aws_secret_key: MinIO secret key
        experiment_name: Name of the MLflow experiment
        data_path: Path to the CSV log dataset
        max_features: Max number of TF-IDF features
        min_df: Minimum document frequency for TF-IDF
        max_df: Maximum document frequency for TF-IDF
        n_clusters: Number of K-Means clusters
        n_init: Number of K-Means initializations
        random_state: Random seed for reproducibility
        k_range: Comma-separated k values to evaluate (e.g. "3,5,8,10")
        model_name: Nom du modèle PyFunc dans MLflow

    Returns:
        run_id: MLflow run ID for downstream components
    """
    # ── Imports (self-contained for KFP container isolation) ──────────
    import mlflow
    import mlflow.sklearn
    import mlflow.pyfunc
    from mlflow.models.signature import infer_signature
    import pandas as pd
    import numpy as np
    import os
    import re
    import warnings

    warnings.filterwarnings("ignore")

    print("=" * 70)
    print("  [Model] Log Clustering Pipeline - TF-IDF + K-Means + MLflow")
    print("=" * 70)

    # ── 1. Configure MLflow tracking URI ──────────────────────────────
    mlflow.set_tracking_uri(mlflow_tracking_uri)
    print(f"MLflow tracking URI: {mlflow_tracking_uri}")

    # ── 2. Configure MinIO environment variables ──────────────────────
    os.environ["MLFLOW_S3_ENDPOINT_URL"] = minio_endpoint
    os.environ["AWS_ACCESS_KEY_ID"] = aws_access_key
    os.environ["AWS_SECRET_ACCESS_KEY"] = aws_secret_key
    print(f"MinIO endpoint configured: {minio_endpoint}")

    # ── 3. Set MLflow experiment ──────────────────────────────────────
    mlflow.set_experiment(experiment_name)
    print(f"Using experiment: {experiment_name}")

    # ══════════════════════════════════════════════════════════════════
    #  Helper functions (defined inside for KFP container isolation)
    # ══════════════════════════════════════════════════════════════════

    def clean_and_extract_patterns(df: pd.DataFrame) -> pd.DataFrame:
        """Nettoyer les messages et extraire des patterns opérationnels."""
        df = df.copy()
        df["message_clean"] = df["message"].astype(str).str.strip().str.lower()

        def _extract_pattern(row):
            parts = []
            parts.append(str(row["method"]).lower())
            endpoint = str(row["endpoint"]).lower()
            endpoint = re.sub(r"/\d+", "/{id}", endpoint)
            parts.append(endpoint.replace("/", "_").strip("_") or "root")
            parts.append(f"status_{int(row['status_code'])}")
            parts.append(str(row["component"]).lower())
            parts.append(str(row["action"]).lower())
            parts.append(str(row["level"]).lower())
            return " ".join(parts)

        df["log_pattern"] = df.apply(_extract_pattern, axis=1)
        return df

    def label_clusters(df: pd.DataFrame, kmeans_model, feature_names_list):
        """Attribuer un label interprétatif à chaque cluster."""
        order_centroids = kmeans_model.cluster_centers_.argsort()[:, ::-1]
        top_words = {}
        cluster_labels = {}

        for cid in range(kmeans_model.n_clusters):
            top_terms = [feature_names_list[idx] for idx in order_centroids[cid, :10]]
            top_words[cid] = top_terms
            cluster_data = df[df["cluster_id"] == cid]

            top_component = (
                cluster_data["component"].mode().iloc[0]
                if len(cluster_data) > 0
                else "unknown"
            )
            top_endpoint = (
                cluster_data["endpoint"].mode().iloc[0]
                if len(cluster_data) > 0
                else "unknown"
            )

            error_flag = any(
                "500" in t or "502" in t or "503" in t for t in top_terms[:5]
            )
            warn_flag = any(
                "400" in t or "401" in t or "403" in t for t in top_terms[:5]
            )

            if error_flag:
                label = f"Erreurs Serveur ({top_component})"
            elif warn_flag:
                label = f"Accès Non Autorisés ({top_component})"
            else:
                label = f"Opérations {top_component.capitalize()} ({top_endpoint})"

            cluster_labels[cid] = label

        df["cluster_label"] = df["cluster_id"].map(cluster_labels)
        return df, cluster_labels, top_words

    def setup_opentelemetry(experiment_name: str):
        import logging
        from opentelemetry import trace, metrics
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
        from opentelemetry._logs import set_logger_provider
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
        from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
        
        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
        
        resource = Resource(attributes={
            "service.name": "dummy-target-app",
            "experiment.name": experiment_name
        })

        tracer_provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(tracer_provider)
        span_processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
        tracer_provider.add_span_processor(span_processor)
        tracer = trace.get_tracer("ml.anomaly.detector")

        metric_reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=endpoint, insecure=True)
        )
        meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        metrics.set_meter_provider(meter_provider)
        meter = metrics.get_meter("ml.anomaly.detector")

        logger_provider = LoggerProvider(resource=resource)
        set_logger_provider(logger_provider)
        log_exporter = OTLPLogExporter(endpoint=endpoint, insecure=True)
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
        
        handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
        otel_logger = logging.getLogger("otel_ml_logger")
        otel_logger.setLevel(logging.INFO)
        if not otel_logger.handlers:
            otel_logger.addHandler(handler)

        return tracer, meter, otel_logger

    def emit_anomaly_events(df, cluster_labels, top_words, tracer, meter, otel_logger):
        from opentelemetry import trace
        anomaly_counter = meter.create_counter(
            "ml_anomaly_detected_total",
            description="Nombre de logs identifiés comme anomalies par le modèle ML"
        )

        for cid, label in cluster_labels.items():
            if "Erreurs Serveur" in label or "Accès Non Autorisés" in label:
                cluster_data = df[df["cluster_id"] == cid]
                anomaly_count = len(cluster_data)
                
                with tracer.start_as_current_span(f"ml_anomaly_detected_{cid}") as span:
                    span.set_attribute("anomaly.type", label)
                    span.set_attribute("anomaly.cluster_id", cid)
                    span.set_attribute("anomaly.count", anomaly_count)
                    
                    trace_id = trace.format_trace_id(span.get_span_context().trace_id)
                    
                    anomaly_counter.add(anomaly_count, {"anomaly_type": label})
                    
                    terms = ", ".join(top_words[cid][:8])
                    otel_logger.error(
                        f"ML Anomaly Detected: {label}. Cluster {cid} contains {anomaly_count} events. Top terms: {terms}",
                        extra={"trace_id": trace_id, "cluster_id": cid, "anomaly_count": anomaly_count}
                    )
                    print(f"   [OTLP] Émis {anomaly_count} anomalies de type '{label}' (TraceID: {trace_id})")

    # ── PyFunc model class (self-contained) ───────────────────────────
    class LogClusteringPipelineModel(mlflow.pyfunc.PythonModel):
        """
        Modèle MLflow customisé (PyFunc) qui encapsule le nettoyage,
        le TF-IDF, et le K-Means en un seul endpoint prêt pour l'API REST.
        """

        def __init__(self, vectorizer, kmeans, cluster_labels):
            self.vectorizer = vectorizer
            self.kmeans = kmeans
            self.cluster_labels = cluster_labels

        def _clean_message(self, msg: str) -> str:
            import re as _re

            if not isinstance(msg, str):
                return ""
            msg = _re.sub(r"\b\d+\b", "<NUM>", msg)
            msg = _re.sub(
                r"([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})",
                "<UUID>",
                msg,
            )
            msg = _re.sub(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b", "<IP>", msg)
            return msg.lower().strip()

        def predict(self, context, model_input):
            import pandas as _pd

            if isinstance(model_input, _pd.DataFrame):
                col = (
                    "message"
                    if "message" in model_input.columns
                    else model_input.columns[0]
                )
                messages = model_input[col].tolist()
            elif isinstance(model_input, list):
                messages = model_input
            else:
                messages = [str(model_input)]

            cleaned = [self._clean_message(m) for m in messages]
            X_pred = self.vectorizer.transform(cleaned)
            preds = self.kmeans.predict(X_pred)
            labels = [self.cluster_labels.get(p, "Unknown") for p in preds]

            return _pd.DataFrame(
                {"cluster_id": preds, "cluster_label": labels}
            )

    # ══════════════════════════════════════════════════════════════════
    #  MLflow Run
    # ══════════════════════════════════════════════════════════════════

    with mlflow.start_run() as run:
        print(f"\nMLflow run started: {run.info.run_id}")

        # ── 4. Load training data ────────────────────────────────────
        print(f"\n[Step 1] Loading data from: {data_path}")
        df = pd.read_csv(data_path)
        print(f"  Data shape: {df.shape}")

        mlflow.log_param("data_path", data_path)
        mlflow.log_param("n_samples", len(df))

        # ── 5. Clean & extract patterns ──────────────────────────────
        print("\n[Step 2] Cleaning & extracting patterns")
        df = clean_and_extract_patterns(df)

        n_unique_patterns = df["log_pattern"].nunique()
        n_unique_messages = df["message_clean"].nunique()
        reduction_pct = (
            (1 - n_unique_patterns / n_unique_messages) * 100
            if n_unique_messages > 0
            else 0
        )
        print(f"  Patterns: {n_unique_patterns} unique (reduction {reduction_pct:.1f}%)")

        mlflow.log_metric("n_unique_patterns", n_unique_patterns)
        mlflow.log_metric("pattern_reduction_pct", round(reduction_pct, 1))

        # ── 6. TF-IDF vectorization ──────────────────────────────────
        print("\n[Step 3] TF-IDF vectorization")
        from sklearn.feature_extraction.text import TfidfVectorizer

        vectorizer = TfidfVectorizer(
            max_features=max_features,
            stop_words="english",
            min_df=min_df,
            max_df=max_df,
            token_pattern=r"(?u)\b\w+\b",
        )
        X = vectorizer.fit_transform(df["log_pattern"])
        feature_names = vectorizer.get_feature_names_out()

        print(f"  TF-IDF matrix: {X.shape[0]} docs × {X.shape[1]} features")

        # Log TF-IDF hyperparameters
        mlflow.log_param("max_features", max_features)
        mlflow.log_param("min_df", min_df)
        mlflow.log_param("max_df", max_df)
        mlflow.log_metric("tfidf_vocabulary_size", len(feature_names))

        # ── 7. Evaluate k-range (elbow + silhouette) ─────────────────
        print("\n[Step 4] Evaluating k-range (elbow + silhouette)")
        from sklearn.cluster import KMeans
        from sklearn.metrics import silhouette_score

        k_values = [int(k.strip()) for k in k_range.split(",")]

        eval_results = {"k": [], "inertia": [], "silhouette": []}
        for k in k_values:
            km = KMeans(n_clusters=k, random_state=random_state, n_init=n_init)
            preds = km.fit_predict(X)
            sil = silhouette_score(X, preds)
            eval_results["k"].append(k)
            eval_results["inertia"].append(km.inertia_)
            eval_results["silhouette"].append(sil)
            print(f"  k={k:2d}: inertia={km.inertia_:10.0f}, silhouette={sil:.3f}")

        best_idx = int(np.argmax(eval_results["silhouette"]))
        best_k = eval_results["k"][best_idx]
        print(f"  → Best k: {best_k} (silhouette={eval_results['silhouette'][best_idx]:.3f})")

        mlflow.log_metric("best_k_silhouette", best_k)
        mlflow.log_metric(
            "best_silhouette_score",
            round(eval_results["silhouette"][best_idx], 4),
        )

        # ── 8. Train final K-Means ───────────────────────────────────
        print(f"\n[Step 5] Training K-Means (k={n_clusters})")
        kmeans_model = KMeans(
            n_clusters=n_clusters,
            random_state=random_state,
            n_init=n_init,
        )
        labels = kmeans_model.fit_predict(X)
        sil_score = silhouette_score(X, labels)
        df["cluster_id"] = labels

        print(
            f"  K-Means (k={n_clusters}) — inertia={kmeans_model.inertia_:.0f}, "
            f"silhouette={sil_score:.3f}"
        )

        # Log K-Means hyperparameters & metrics
        mlflow.log_param("n_clusters", n_clusters)
        mlflow.log_param("n_init", n_init)
        mlflow.log_param("random_state", random_state)
        mlflow.log_param("k_range", k_range)
        mlflow.log_metric("silhouette_score", round(sil_score, 4))
        mlflow.log_metric("inertia", round(kmeans_model.inertia_, 2))
        print("  Parameters & metrics logged to MLflow")

        # ── 9. Label clusters ────────────────────────────────────────
        print("\n[Step 6] Labeling & interpreting clusters")
        df, cluster_labels_map, top_words = label_clusters(
            df, kmeans_model, feature_names
        )

        for cid, label in cluster_labels_map.items():
            mlflow.log_param(f"cluster_{cid}_label", label)
            print(f"  Cluster {cid}: {label}")

        # ── Step 6.5 : OTLP Anomaly Events ───────────────────────────
        print("\n[Step 6.5] Émission d'événements d'anomalies (OTLP)")
        tracer, meter, otel_logger = setup_opentelemetry(experiment_name)
        emit_anomaly_events(df, cluster_labels_map, top_words, tracer, meter, otel_logger)

        # Part des logs dans des clusters « Erreurs » (0–1), pour quality gate validate_model
        error_cluster_mask = df["cluster_label"].str.contains(
            "Erreurs", case=False, na=False
        )
        anomaly_rate = float(error_cluster_mask.mean()) if len(df) > 0 else 0.0
        mlflow.log_metric("anomaly_rate", round(anomaly_rate, 6))
        print(
            f"  anomaly_rate (part logs clusters Erreurs): {anomaly_rate:.4f} "
            f"({anomaly_rate * 100:.2f} %)"
        )

        # ── 10. Export summary CSV ───────────────────────────────────
        print("\n[Step 7] Exporting cluster summary")
        import tempfile

        rows = []
        for cid in range(kmeans_model.n_clusters):
            cluster_data = df[df["cluster_id"] == cid]
            rows.append(
                {
                    "ClusterID": cid,
                    "Label": cluster_labels_map.get(cid, "Unknown"),
                    "TopTerms": ", ".join(top_words[cid][:8]),
                    "ExampleLog": (
                        cluster_data["message"].iloc[0]
                        if len(cluster_data) > 0
                        else ""
                    ),
                    "Count": int(len(cluster_data)),
                    "Percentage": round(len(cluster_data) / len(df) * 100, 1),
                    "AvgResponseTime": round(
                        cluster_data["response_time_ms"].mean(), 1
                    ),
                }
            )

        summary = pd.DataFrame(rows).sort_values("Count", ascending=False)
        summary_path = os.path.join(tempfile.mkdtemp(), "log_clusters_summary.csv")
        summary.to_csv(summary_path, index=False)
        mlflow.log_artifact(summary_path, "outputs")
        print(f"  Summary exported & logged to MLflow: {summary_path}")

        # ── 11. Log TF-IDF vectorizer to MLflow ─────────────────────
        print("\n[Step 8] Logging models to MLflow")
        mlflow.sklearn.log_model(
            sk_model=vectorizer,
            artifact_path="tfidf_vectorizer",
        )
        print("  TF-IDF vectorizer logged")

        # ── 12. Log PyFunc pipeline model to MLflow ──────────────────
        input_example = pd.DataFrame(
            {"message": ["level=error msg='connection refused'"]}
        )
        output_example = pd.DataFrame(
            {"cluster_id": [0], "cluster_label": ["Erreurs Serveur"]}
        )
        signature = infer_signature(input_example, output_example)

        mlflow.pyfunc.log_model(
            artifact_path="loki_pipeline_model",
            python_model=LogClusteringPipelineModel(
                vectorizer, kmeans_model, cluster_labels_map
            ),
            signature=signature,
            input_example=input_example,
        )
        print("  PyFunc pipeline model logged to MLflow artifact store")

        # Pas d'artefact KFP « model » : le modèle complet est dans MLflow/MinIO ;
        # cela évite un gros upload vers le dépôt d'artefacts du workflow (SeaweedFS / S3 KFP).

        # ── Result ───────────────────────────────────────────────────
        run_id = run.info.run_id
        print("\n" + "=" * 70)
        print("  [SUCCESS] TRAINING COMPLETE")
        print("=" * 70)
        print(f"  Total logs processed  : {len(df):,}")
        print(f"  Clusters identified   : {kmeans_model.n_clusters}")
        print(f"  TF-IDF vocabulary     : {len(feature_names)} terms")
        print(f"  Silhouette score      : {sil_score:.3f}")
        print(f"  Inertia               : {kmeans_model.inertia_:.0f}")
        print(f"  MLflow experiment     : {experiment_name}")
        print(f"  MLflow run ID         : {run_id}")
        print("=" * 70)

        # ── 13. Return the MLflow run_id ─────────────────────────────
        return run_id
