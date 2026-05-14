# B — Erreur MySQL Collation `utf8mb3` / Error 3988

## Symptôme

Lors de la création d'un Run dans l'interface Kubeflow, une erreur interne apparaît :

- Code d'erreur `3988` ou `1366`
- Message : `InternalServerError`
- Les étapes du pipeline sont introuvables (`Cannot find context`)

## Cause

La base de données MySQL est configurée en `utf8mb3` (pour la compatibilité d'authentification avec Kubeflow), mais le code source de vos composants Python contient des **emojis** (ex: `📦`, `🤖`, `✅`).

Le code des composants étant stocké dans la base MySQL (dans le `PipelineRuntimeManifest`), la présence de caractères sur 4 octets fait planter la base de données.

## Solution

**1. Supprimer tous les emojis** de vos fichiers Python :

```bash
# Fichiers concernés :
# - ml/ml-log-loki/kubeflow/train_model.py
# - ml/ml-log-loki/kubeflow/register_model.py
# - ml/ml-log-loki/kubeflow/pipeline.py
```

Remplacez les emojis par du texte ASCII équivalent. Exemples :

| Avant | Après |
|---|---|
| `📦 Installation des dépendances` | `[INSTALL] Installation des dépendances` |
| `🤖 Entraînement du modèle` | `[TRAIN] Entraînement du modèle` |
| `✅ Succès` | `[SUCCESS] Succès` |

**2. Recompiler le pipeline :**

```bash
cd ml/ml-log-loki/kubeflow
python pipeline.py
# → Regénère log_clustering_pipeline.yaml
```

**3. Créer un NOUVEAU Run** dans l'interface Kubeflow avec le nouveau fichier YAML compilé.

!!! warning "Ne pas réutiliser un ancien Run"
    Modifier un Run existant ne suffit pas. Il faut impérativement créer un **nouveau Run** avec le pipeline recompilé.
