# G — Impossible de créer un Run — MySQL charset & utilisateur

## Symptôme

L'interface Kubeflow affiche une erreur lors de la création d'un Run, ou les runs restent bloqués sans progresser. Les logs de `ml-pipeline` montrent des erreurs MySQL liées à l'encodage ou à l'authentification.

## Cause

Trois problèmes MySQL combinés empêchent Kubeflow Pipelines de fonctionner :

| # | Problème | Impact |
|---|---|---|
| **1** | Base `mlpipeline` en charset `utf8mb3` au lieu de `utf8mb4` | Crash sur les caractères spéciaux (emojis, noms de paramètres) |
| **2** | Tables `runs` / `pipelines` non converties en `utf8mb4` | Erreur 3988 ou 1366 lors de l'insertion |
| **3** | Utilisateur `kubeflow` absent ou avec mauvais plugin d'auth | Connexion refusée par `ml-pipeline` |

!!! important "Appliquer les 3 corrections ensemble et dans l'ordre"
    Un seul oubli suffit à maintenir le bug.

## Fix complet — Procédure pas à pas (vérifié)

### Étape 1 — Se connecter à MySQL

```bash
kubectl exec -it deploy/mysql -n kubeflow -- mysql -uroot -p
```

### Étape 2 — Créer la base (si nécessaire)

```sql
CREATE DATABASE IF NOT EXISTS mlpipeline;
```

### Étape 3 — Fix charset UTF-8 (critique)

```sql
ALTER DATABASE mlpipeline
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
```

### Étape 4 — Convertir les tables principales

```sql
ALTER TABLE mlpipeline.runs
  CONVERT TO CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

ALTER TABLE mlpipeline.pipelines
  CONVERT TO CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
```

### Étape 5 — Créer l'utilisateur Kubeflow (si absent)

```sql
CREATE USER 'kubeflow'@'%'
  IDENTIFIED WITH mysql_native_password
  BY 'kubeflow';
```

### Étape 6 — Donner les droits

```sql
GRANT ALL PRIVILEGES ON mlpipeline.* TO 'kubeflow'@'%';
```

### Étape 7 — Appliquer les changements

```sql
FLUSH PRIVILEGES;
```

### Étape 8 — Vérification de l'utilisateur

```sql
SELECT user, host, plugin
FROM mysql.user
WHERE user='kubeflow';
```

Résultat attendu :

```
+---------+------+-----------------------+
| user    | host | plugin                |
+---------+------+-----------------------+
| kubeflow| %    | mysql_native_password |
+---------+------+-----------------------+
```

### Étape 9 — (Optionnel) Vérifier le charset du serveur

```sql
SHOW VARIABLES LIKE 'character_set%';
```

Les valeurs `character_set_database` et `character_set_server` doivent afficher `utf8mb4`.

### Étape 10 — Redémarrer Kubeflow après le fix

```bash
kubectl rollout restart deployment ml-pipeline -n kubeflow
kubectl rollout restart deployment metadata-grpc-deployment -n kubeflow
```

## Vérification finale

Dans l'UI Kubeflow → **Pipelines** → **Create Run** :

Le run doit passer successivement par les états : `CREATED` → `RUNNING` → `SUCCESS`

## Résumé des 3 conditions à valider

```
Pour que Kubeflow Pipelines fonctionne, ces 3 conditions doivent etre remplies :

  1. Base mlpipeline
     - CHARACTER SET = utf8mb4
     - Tables runs + pipelines converties

  2. Utilisateur MySQL
     - kubeflow@%
     - plugin = mysql_native_password

  3. Permissions
     - ALL PRIVILEGES ON mlpipeline.*
```

!!! tip "Si les tables n'existent pas encore"
    Si les tables `runs` ou `pipelines` n'existent pas encore au moment du fix (premier démarrage de Kubeflow), l'**étape 4 peut être ignorée** — les tables seront créées directement avec le bon charset. Relancez l'étape 4 après le premier démarrage de `ml-pipeline` si des erreurs de collation persistent.
