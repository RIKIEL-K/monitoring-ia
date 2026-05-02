"""
Log Clustering for Pattern Discovery — Loki Logs (Reproducible Script)

Pipeline TF-IDF + K-Means sur les logs collectés depuis Loki.
Intègre MLflow pour le tracking des expériences et MinIO comme artifact store S3.

Usage:
    python scripts/train_log_clustering.py --help
    python scripts/train_log_clustering.py --csv-path datasets/mock_loki_logs.csv --n-clusters 5
    python scripts/train_log_clustering.py --n-clusters 8 --max-features 150 --experiment-name test-clustering
"""

import argparse
import os
import sys
import re
import warnings
from datetime import datetime

import numpy as np
import pandas as pd

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
import mlflow
import mlflow.sklearn
import mlflow.pyfunc
from mlflow.models.signature import infer_signature
from dotenv import load_dotenv

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Résolution des chemins
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, os.pardir))

# Charger .env depuis le répertoire du projet
load_dotenv(os.path.join(PROJECT_DIR, ".env"))


# ===================================================================
# 1 — Argument Parser
# ===================================================================

def str2bool(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')

def parse_args() -> argparse.Namespace:
    """Définir et parser les arguments CLI."""
    parser = argparse.ArgumentParser(
        description="Log Clustering Pipeline — TF-IDF + K-Means avec MLflow tracking",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # --- Données ---
    parser.add_argument(
        "--csv-path",
        type=str,
        default=os.path.join(PROJECT_DIR, "datasets", "mock_loki_logs.csv"),
        help="Chemin vers le dataset CSV des logs Loki",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=os.path.join(PROJECT_DIR, "datasets"),
        help="Répertoire de sortie pour le CSV résumé et les plots",
    )

    # --- TF-IDF ---
    parser.add_argument("--max-features", type=int, default=100, help="Nombre max de features TF-IDF")
    parser.add_argument("--min-df", type=int, default=2, help="Fréquence document minimale TF-IDF")
    parser.add_argument("--max-df", type=float, default=0.95, help="Fréquence document maximale TF-IDF")

    # --- K-Means ---
    parser.add_argument("--n-clusters", type=int, default=5, help="Nombre de clusters K-Means")
    parser.add_argument("--n-init", type=int, default=10, help="Nombre d'initialisations K-Means")
    parser.add_argument("--random-state", type=int, default=42, help="Seed pour reproductibilité")

    # --- Évaluation ---
    parser.add_argument(
        "--k-range",
        type=str,
        default="3,5,8,10,12,15",
        help="Valeurs de k à évaluer (séparées par des virgules)",
    )

    # --- MLflow ---
    parser.add_argument(
        "--experiment-name",
        type=str,
        default="log-clustering-loki",
        help="Nom de l'expérience MLflow",
    )
    parser.add_argument(
        "--run-name",
        type=str,
        default="",
        help="Nom du run MLflow (auto-généré si non spécifié)",
    )

    # --- Model Registry ---
    parser.add_argument(
        "--register-model",
        type=str2bool,
        nargs='?',
        const=True,
        default=False,
        help="Enregistrer le modèle dans le MLflow Model Registry (stocké sur MinIO)",
    )
    parser.add_argument(
        "--model-name",
        type=str,
        default="log-clustering-kmeans",
        help="Nom du modèle dans le Model Registry (défaut : log-clustering-kmeans)",
    )
    parser.add_argument(
        "--promote-to-production",
        type=str2bool,
        nargs='?',
        const=True,
        default=False,
        help="Promouvoir automatiquement la nouvelle version en stage Production",
    )

    return parser.parse_args()


def print_header(text: str):
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)


def print_step(step_num: int, text: str):
    print(f"\n[Step {step_num}] {text}")



def load_data(csv_path: str) -> pd.DataFrame:
    """Charger le dataset CSV des logs."""
    if not os.path.isfile(csv_path):
        raise FileNotFoundError(f"Dataset introuvable : {csv_path}")

    df = pd.read_csv(csv_path)
    print(f"   ✓ Dataset chargé : {len(df):,} lignes, colonnes : {list(df.columns)}")
    return df


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

    n_unique = df["log_pattern"].nunique()
    n_msg = df["message_clean"].nunique()
    reduction = (1 - n_unique / n_msg) * 100 if n_msg > 0 else 0

    print(f"  Patterns extraits : {n_unique} uniques (réduction {reduction:.1f}%)")
    return df



def vectorize_tfidf(df: pd.DataFrame, max_features: int, min_df: int, max_df: float):
    """Convertir les patterns en vecteurs TF-IDF."""
    vectorizer = TfidfVectorizer(
        max_features=max_features,
        stop_words="english",
        min_df=min_df,
        max_df=max_df,
        token_pattern=r"(?u)\b\w+\b",
    )
    X = vectorizer.fit_transform(df["log_pattern"])
    feature_names = vectorizer.get_feature_names_out()

    print(f"   ✓ Matrice TF-IDF : {X.shape[0]:,} docs × {X.shape[1]} features")
    return X, vectorizer, feature_names


def run_kmeans(X, n_clusters: int, n_init: int, random_state: int):
    """Entraîner K-Means et retourner le modèle + prédictions."""
    kmeans = KMeans(n_clusters=n_clusters, random_state=random_state, n_init=n_init)
    labels = kmeans.fit_predict(X)
    sil = silhouette_score(X, labels)
    print(f"   ✓ K-Means (k={n_clusters}) — inertia={kmeans.inertia_:.0f}, silhouette={sil:.3f}")
    return kmeans, labels, sil



def evaluate_k_range(X, k_values: list, n_init: int, random_state: int) -> dict:
    """Évaluer plusieurs valeurs de k (elbow + silhouette)."""
    results = {"k": [], "inertia": [], "silhouette": []}
    for k in k_values:
        model = KMeans(n_clusters=k, random_state=random_state, n_init=n_init)
        preds = model.fit_predict(X)
        sil = silhouette_score(X, preds)
        results["k"].append(k)
        results["inertia"].append(model.inertia_)
        results["silhouette"].append(sil)
        print(f"   k={k:2d}: inertia={model.inertia_:10.0f}, silhouette={sil:.3f}")

    best_idx = int(np.argmax(results["silhouette"]))
    best_k = results["k"][best_idx]
    print(f"   ✓ K recommandé : {best_k} (silhouette={results['silhouette'][best_idx]:.3f})")
    return results


def label_clusters(df: pd.DataFrame, kmeans, feature_names) -> tuple:
    """Attribuer un label interprétatif à chaque cluster."""
    order_centroids = kmeans.cluster_centers_.argsort()[:, ::-1]
    top_words = {}
    cluster_labels = {}

    for cid in range(kmeans.n_clusters):
        top_terms = [feature_names[idx] for idx in order_centroids[cid, :10]]
        top_words[cid] = top_terms
        cluster_data = df[df["cluster_id"] == cid]

        top_component = cluster_data["component"].mode().iloc[0] if len(cluster_data) > 0 else "unknown"
        top_endpoint = cluster_data["endpoint"].mode().iloc[0] if len(cluster_data) > 0 else "unknown"

        error_flag = any("500" in t or "502" in t or "503" in t for t in top_terms[:5])
        warn_flag = any("400" in t or "401" in t or "403" in t for t in top_terms[:5])

        if error_flag:
            label = f"Erreurs Serveur ({top_component})"
        elif warn_flag:
            label = f"Accès Non Autorisés ({top_component})"
        else:
            label = f"Opérations {top_component.capitalize()} ({top_endpoint})"

        cluster_labels[cid] = label

    df["cluster_label"] = df["cluster_id"].map(cluster_labels)
    return df, cluster_labels, top_words



def export_summary(
    df: pd.DataFrame, kmeans, cluster_labels: dict, top_words: dict, output_dir: str
) -> str:
    """Construire et exporter le résumé des clusters."""
    os.makedirs(output_dir, exist_ok=True)

    rows = []
    for cid in range(kmeans.n_clusters):
        cluster_data = df[df["cluster_id"] == cid]
        rows.append(
            {
                "ClusterID": cid,
                "Label": cluster_labels.get(cid, "Unknown"),
                "TopTerms": ", ".join(top_words[cid][:8]),
                "ExampleLog": cluster_data["message"].iloc[0] if len(cluster_data) > 0 else "",
                "Count": int(len(cluster_data)),
                "Percentage": round(len(cluster_data) / len(df) * 100, 1),
                "AvgResponseTime": round(cluster_data["response_time_ms"].mean(), 1),
            }
        )

    summary = pd.DataFrame(rows).sort_values("Count", ascending=False)
    out_path = os.path.join(output_dir, "log_clusters_summary.csv")
    summary.to_csv(out_path, index=False)
    print(f" Résumé exporté : {out_path}")
    return out_path


def setup_mlflow():
    """Configurer MLflow avec MinIO comme artifact store S3."""
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
    mlflow.set_tracking_uri(tracking_uri)

    # Configuration MinIO pour les artifacts S3
    s3_endpoint = os.getenv("MLFLOW_S3_ENDPOINT_URL", "http://localhost:9000")
    os.environ["MLFLOW_S3_ENDPOINT_URL"] = s3_endpoint
    os.environ["AWS_ACCESS_KEY_ID"] = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    os.environ["AWS_SECRET_ACCESS_KEY"] = os.getenv("MINIO_SECRET_KEY", "minioadmin")

    print(f"  MLflow tracking : {tracking_uri}")
    print(f"  MinIO endpoint  : {s3_endpoint}")


def _set_model_stage(model_name: str, model_info, target_stage: str):
    """
    Transitionner une version du modèle vers un stage donné dans le Model Registry.
    Archive toutes les versions précédentes dans ce stage.

    Stages valides : Staging, Production, Archived
    """
    client = mlflow.MlflowClient()

    model_version = client.get_model_version(
        name=model_name,
        version=model_info.registered_model_version,
    )

    # Archiver les versions actuellement dans le stage cible
    existing = client.get_latest_versions(model_name, stages=[target_stage])
    for v in existing:
        client.transition_model_version_stage(
            name=model_name,
            version=v.version,
            stage="Archived",
        )
        print(f"  Version {v.version} archivée (ex-{target_stage})")

    # Transitionner la nouvelle version
    client.transition_model_version_stage(
        name=model_name,
        version=model_version.version,
        stage=target_stage,
    )
    print(f"  ✅ Version {model_version.version} → {target_stage}")
    print(f"     Model URI : models:/{model_name}/{target_stage}")


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
        import re
        if not isinstance(msg, str):
            return ""
        msg = re.sub(r"\b\d+\b", "<NUM>", msg)
        msg = re.sub(r"([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})", "<UUID>", msg)
        msg = re.sub(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b", "<IP>", msg)
        return msg.lower().strip()

    def predict(self, context, model_input):
        import pandas as pd
        
        # MLflow REST API envoie généralement un DataFrame Pandas
        if isinstance(model_input, pd.DataFrame):
            col = "message" if "message" in model_input.columns else model_input.columns[0]
            messages = model_input[col].tolist()
        elif isinstance(model_input, list):
            messages = model_input
        else:
            messages = [str(model_input)]

        # 1. Nettoyage
        cleaned = [self._clean_message(m) for m in messages]
        # 2. TF-IDF
        X = self.vectorizer.transform(cleaned)
        # 3. K-Means
        preds = self.kmeans.predict(X)
        
        # 4. Ajout des labels lisibles
        labels = [self.cluster_labels.get(p, "Unknown") for p in preds]
        
        return pd.DataFrame({
            "cluster_id": preds,
            "cluster_label": labels
        })


def main() -> int:
    args = parse_args()

    print_header("🤖 Log Clustering Pipeline — TF-IDF + K-Means + MLflow")

    # --- Step 1 : Setup MLflow ---
    print_step(1, "Configuration MLflow + MinIO")
    setup_mlflow()
    mlflow.set_experiment(args.experiment_name)

    run_name = args.run_name or f"kmeans-k{args.n_clusters}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    with mlflow.start_run(run_name=run_name):

        # Log tous les hyperparamètres
        mlflow.log_param("csv_path", args.csv_path)
        mlflow.log_param("n_clusters", args.n_clusters)
        mlflow.log_param("max_features", args.max_features)
        mlflow.log_param("min_df", args.min_df)
        mlflow.log_param("max_df", args.max_df)
        mlflow.log_param("n_init", args.n_init)
        mlflow.log_param("random_state", args.random_state)

        # --- Step 2 : Chargement ---
        print_step(2, "Chargement du dataset")
        df = load_data(args.csv_path)
        mlflow.log_param("n_samples", len(df))

        # --- Step 3 : Nettoyage & patterns ---
        print_step(3, "Nettoyage & extraction de patterns")
        df = clean_and_extract_patterns(df)
        n_unique_patterns = df["log_pattern"].nunique()
        n_unique_messages = df["message_clean"].nunique()
        reduction_pct = (1 - n_unique_patterns / n_unique_messages) * 100 if n_unique_messages > 0 else 0
        mlflow.log_metric("n_unique_patterns", n_unique_patterns)
        mlflow.log_metric("pattern_reduction_pct", round(reduction_pct, 1))

        # --- Step 4 : TF-IDF ---
        print_step(4, "Vectorisation TF-IDF")
        X, vectorizer, feature_names = vectorize_tfidf(df, args.max_features, args.min_df, args.max_df)
        mlflow.log_metric("tfidf_vocabulary_size", len(feature_names))

        # --- Step 5 : Évaluation k-range ---
        print_step(5, "Évaluation Elbow + Silhouette")
        k_values = [int(k) for k in args.k_range.split(",")]
        eval_results = evaluate_k_range(X, k_values, args.n_init, args.random_state)

        best_idx = int(np.argmax(eval_results["silhouette"]))
        mlflow.log_metric("best_k_silhouette", eval_results["k"][best_idx])
        mlflow.log_metric("best_silhouette_score", round(eval_results["silhouette"][best_idx], 4))

        # --- Step 6 : K-Means final ---
        print_step(6, f"Clustering K-Means (k={args.n_clusters})")
        kmeans, labels, sil_score = run_kmeans(X, args.n_clusters, args.n_init, args.random_state)
        df["cluster_id"] = labels

        mlflow.log_metric("silhouette_score", round(sil_score, 4))
        mlflow.log_metric("inertia", round(kmeans.inertia_, 2))

        # --- Step 7 : Labeling ---
        print_step(7, "Labeling & interprétation des clusters")
        df, cluster_labels, top_words = label_clusters(df, kmeans, feature_names)

        for cid, label in cluster_labels.items():
            mlflow.log_param(f"cluster_{cid}_label", label)

        # --- Step 8 : Export ---
        print_step(8, "Export du résumé")
        summary_path = export_summary(df, kmeans, cluster_labels, top_words, args.output_dir)
        mlflow.log_artifact(summary_path, "outputs")

        # --- Step 9 : Log + enregistrement du modèle ---
        print_step(9, "Enregistrement du modèle (Pipeline PyFunc) dans MLflow + MinIO")

        # Vectorizer : toujours loggé seul comme artifact (optionnel, pour debug)
        mlflow.sklearn.log_model(
            sk_model=vectorizer,
            artifact_path="tfidf_vectorizer",
        )

        # Création de la signature d'entrée/sortie pour l'API REST
        input_example = pd.DataFrame({"message": ["level=error msg='connection refused'"]})
        output_example = pd.DataFrame({"cluster_id": [0], "cluster_label": ["Erreurs Serveur"]})
        signature = infer_signature(input_example, output_example)

        # PyFunc : Enregistrement du pipeline complet prêt pour l'API
        registered_model_name = args.model_name if args.register_model else None
        
        model_info = mlflow.pyfunc.log_model(
            artifact_path="loki_pipeline_model",
            python_model=LogClusteringPipelineModel(vectorizer, kmeans, cluster_labels),
            signature=signature,
            registered_model_name=registered_model_name,
            input_example=input_example
        )
        print(f"  Pipeline PyFunc loggé — artifact URI : {model_info.model_uri}")

        if args.register_model:
            print(f"  Modèle enregistré dans le registry sous : {args.model_name}")

            # Stage par défaut : Staging
            print_step(10, "Transition du modèle vers Staging (stage par défaut)")
            _set_model_stage(args.model_name, model_info, "Staging")

            # Promotion vers Production si explicitement demandée
            if args.promote_to_production:
                print_step(11, "Promotion du modèle vers Production")
                _set_model_stage(args.model_name, model_info, "Production")

        # --- Récapitulatif ---
        print_header("ANALYSE DES LOGS LOKI — TERMINÉE")
        print(f"  Total logs traités    : {len(df):,}")
        print(f"  Clusters identifiés   : {kmeans.n_clusters}")
        print(f"  Vocabulaire TF-IDF    : {len(feature_names)} termes")
        print(f"  Silhouette score      : {sil_score:.3f}")
        print(f"  Inertia               : {kmeans.inertia_:.0f}")
        print(f"  MLflow experiment     : {args.experiment_name}")
        print(f"  MLflow run            : {run_name}")
        if args.register_model:
            stage = "Production" if args.promote_to_production else "Staging"
            print(f"  Model Registry        : {args.model_name}")
            print(f"  Stage                 : {stage} ✅")
        print()
        print("  ✅ Chargement et exploration du dataset Loki")
        print("  ✅ Nettoyage et extraction de patterns")
        print("  ✅ Vectorisation TF-IDF")
        print("  ✅ Évaluation Elbow + Silhouette")
        print("  ✅ Clustering K-Means")
        print("  ✅ Labeling & interprétation")
        print("  ✅ Export du résumé CSV")
        print("  ✅ Modèles loggés dans MLflow (MinIO)")
        print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
