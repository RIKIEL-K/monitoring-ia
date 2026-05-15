# Guide de déploiement EC2 — OpenTelemetry Collector + App Flask

Commandes à exécuter **sur l'EC2 cible** (où tourne l'application).

> **Contexte** : OpenTelemetry Collector tourne via **systemd** (`otelcol.service`) sous l'utilisateur **`otel`** (non-root). Les variables d'environnement sont chargées depuis `/etc/otelcol/otelcol.conf`. On se contente de mettre à jour la config et de déployer l'app Docker.

---

## Prérequis — Vérifier que le collector tourne

```bash
# Vérifier l'état du service
sudo systemctl status otelcol

# Vérifier que le port gRPC est bien en écoute
ss -tlnp | grep 4317

# Vérifier la version installée
otelcol --version
```

> Si le service n'est **pas** trouvé, le nom du service systemd est peut-être différent :
> ```bash
> sudo systemctl list-units --type=service | grep otel
> ```

---

## Étape 1 — Vérifier le service systemd existant

Le service installé est le suivant (ne pas modifier) :

```ini
# /usr/lib/systemd/system/otelcol.service
[Unit]
Description=OpenTelemetry Collector
After=network.target

[Service]
EnvironmentFile=/etc/otelcol/otelcol.conf      # ← variables d'env ici
ExecStart=/usr/bin/otelcol $OTELCOL_OPTIONS    # ← options injectées via otelcol.conf
ExecReload=/bin/kill -HUP $MAINPID
KillMode=mixed
Restart=on-failure
Type=simple
User=otel                                       # ← tourne sous l'utilisateur otel
Group=otel

[Install]
WantedBy=multi-user.target
```

```bash
# Voir le fichier de config et les options actuelles
cat /etc/otelcol/otelcol.conf
```

---

## Étape 2 — Mettre à jour le fichier de configuration

```bash
# Copier la nouvelle config depuis le projet cloné
sudo cp ~/monitoring-ia/ec2-target-app/otel-collector-config.yaml /etc/otelcol/config.yaml

# S'assurer que l'utilisateur otel peut lire le fichier
sudo chown otel:otel /etc/otelcol/config.yaml

# --- OU écrire directement le contenu ---
sudo tee /etc/otelcol/config.yaml > /dev/null << 'EOF'

receivers:

  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

  filelog:
    # ⚠️ Le service tourne sous l'user 'otel' — ce dossier doit être lisible par otel
    # sudo chown -R otel:otel /home/ubuntu/monitoring-ia/ec2-target-app/target-logs
    include: [/home/ubuntu/monitoring-ia/ec2-target-app/target-logs/*.log]
    start_at: end
    operators:
      - type: json_parser
        timestamp:
          parse_from: attributes.timestamp
          layout: "%Y-%m-%dT%H:%M:%S.%f%z"
        severity:
          parse_from: attributes.level

  hostmetrics:
    collection_interval: 15s
    scrapers:
      cpu: {}
      memory: {}
      disk: {}
      network: {}
      filesystem: {}

processors:
  resourcedetection:
    detectors: [env, system]
    timeout: 2s
    override: false

  batch:
    send_batch_size: 1000
    timeout: 5s

exporters:
  otlp/jaeger:
    endpoint: "http://${env:JAEGER_IP}:4317"
    tls:
      insecure: true

  prometheusremotewrite:
    endpoint: "http://${env:OBSERVABILITY_IP}:9090/api/v1/write"
    tls:
      insecure: true

  loki:
    endpoint: "http://${env:OBSERVABILITY_IP}:3100/loki/api/v1/push"

service:
  telemetry:
    logs:
      level: info

  pipelines:
    traces:
      receivers: [otlp]
      processors: [resourcedetection, batch]
      exporters: [otlp/jaeger]

    metrics:
      receivers: [otlp, hostmetrics]
      processors: [resourcedetection, batch]
      exporters: [prometheusremotewrite]

    logs:
      receivers: [otlp, filelog]
      processors: [resourcedetection, batch]
      exporters: [loki]
EOF
```

---

## Étape 3 — Ajouter les variables d'environnement dans `otelcol.conf`

Le fichier de config utilise `${env:OBSERVABILITY_IP}` et `${env:JAEGER_IP}`.
Ce service charge ses variables depuis **`/etc/otelcol/otelcol.conf`** (pas dans le `.service`).

```bash
# Voir le contenu actuel
cat /etc/otelcol/otelcol.conf

# 1. Ouvre le fichier avec l'éditeur texte "nano"
sudo nano /etc/otelcol/otelcol.conf

# 2. Supprime tout ce qu'il y a dedans et copie-colle ceci :
# (n'oublie pas de remplacer les <IP_...> par tes vraies adresses IP)

OTELCOL_OPTIONS="--config=/etc/otelcol/config.yaml"
OBSERVABILITY_IP="<IP_DE_TON_EC2_OBSERVABILITE>"
JAEGER_IP="<IP_DE_TON_EC2_OBSERVABILITE>"

# 3. Sauvegarde et quitte : 
# Fais Ctrl+O, appuie sur Entrée, puis Ctrl+X.

# S'assurer que l'utilisateur otel peut lire le fichier
sudo chown otel:otel /etc/otelcol/otelcol.conf
sudo chmod 640 /etc/otelcol/otelcol.conf
```

> **Pourquoi `otelcol.conf` ?** Le service systemd déclare `EnvironmentFile=/etc/otelcol/otelcol.conf`.
> Toutes les variables déclarées dans ce fichier sont injectées comme variables d'environnement
> lors du démarrage, et deviennent accessibles dans `config.yaml` via `${env:NOM_VAR}`.

> **Permissions** : Le service tourne sous l'utilisateur `otel`. S'assurer que les logs
> de l'application sont aussi lisibles par cet utilisateur :
> ```bash
> sudo chown -R otel:otel /home/ubuntu/monitoring-ia/ec2-target-app/target-logs
> ```

---

## Étape 4 — Valider la config et redémarrer le service

```bash
# Valider la syntaxe du fichier YAML avant de redémarrer
otelcol --config=/etc/otelcol/config.yaml validate

# Recharger systemd et redémarrer le collector
sudo systemctl daemon-reload
sudo systemctl restart otelcol

# Vérifier que le service est bien "active (running)"
sudo systemctl status otelcol

# Suivre les logs en temps réel pour détecter d'éventuelles erreurs
sudo journalctl -u otelcol -f
```

---

## Étape 5 — Démarrer l'application Docker

```bash
cd ~/monitoring-ia/ec2-target-app

# Reconstruire l'image avec les nouvelles dépendances OTEL et démarrer
docker-compose up -d --build

# Vérifier que le conteneur tourne
docker ps

# Voir les logs de l'app Flask
docker-compose logs -f dummy-app
```

---

## Étape 6 — Valider la télémétrie de bout en bout

```bash
# Générer du trafic pour créer des traces, logs et métriques
curl http://localhost:8080/api/health
curl http://localhost:8080/api/generate-error
curl http://localhost:8080/api/login-failed
curl http://localhost:8080/api/payment-timeout

# Vérifier les exports dans les logs du collector
sudo journalctl -u otelcol --since "1 minute ago"
```

Dans **Grafana**, vérifie :

| Backend     | Requête de test                              |
|-------------|----------------------------------------------|
| **Loki**    | `{service_name="dummy-target-app"}`          |
| **Prometheus** | `otelcol_exporter_sent_metric_points`     |
| **Jaeger**  | Service → `dummy-target-app`                 |

---

## Commandes de diagnostic rapide

```bash
# État du service collector
sudo systemctl status otelcol

# Logs en temps réel
sudo journalctl -u otelcol -f

# Port gRPC ouvert ?
ss -tlnp | grep 4317

# Logs du conteneur Docker
docker-compose -f ~/monitoring-ia/ec2-target-app/docker-compose.yml logs -f dummy-app

# Joignabilité de l'EC2 Observabilité
OBSERVABILITY_IP="<ton_ip>"
curl -s http://${OBSERVABILITY_IP}:9090/-/healthy   # Prometheus
curl -s http://${OBSERVABILITY_IP}:3100/ready        # Loki
curl -s http://${OBSERVABILITY_IP}:16686/            # Jaeger UI
```
