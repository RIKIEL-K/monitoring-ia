# EC2 Target App — Stack de Télémétrie OpenTelemetry

Cette application Flask génère des logs structurés, des métriques et des traces
qui sont collectés par un **OpenTelemetry Collector en mode agent** (systemd) installé
directement sur l'EC2, puis acheminés vers la stack d'observabilité.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        EC2 — Machine Cible                       │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │               Docker Compose                                │ │
│  │                                                             │ │
│  │  ┌──────────────────────────────────────────────────────┐  │ │
│  │  │  dummy-app  (Flask + opentelemetry-instrument)       │  │ │
│  │  │                                                      │  │ │
│  │  │  • Auto-instrumentation Flask (traces HTTP)          │  │ │
│  │  │  • Logs JSON structurés → /app/logs/dummy-app.log   │  │ │
│  │  │  • Envoi OTLP gRPC → host.docker.internal:4317      │  │ │
│  │  └──────────────────────┬───────────────────────────────┘  │ │
│  │                         │ OTLP gRPC                        │ │
│  └─────────────────────────┼───────────────────────────────────┘ │
│                            │ host.docker.internal = hôte EC2      │
│                            ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │       OpenTelemetry Collector — Mode Agent (systemd)        │  │
│  │                                                             │  │
│  │  Receivers :                                                │  │
│  │    • otlp (grpc :4317, http :4318)  ← app Flask            │  │
│  │    • filelog (/target-logs/*.log)   ← logs fichier         │  │
│  │    • hostmetrics                    ← CPU, RAM, disque      │  │
│  │                                                             │  │
│  │  Processors :                                               │  │
│  │    resourcedetection → batch                                │  │
│  │                                                             │  │
│  │  Pipelines :                                                │  │
│  │    traces  → otlp/jaeger                                   │  │
│  │    metrics → prometheusremotewrite                          │  │
│  │    logs    → loki                                           │  │
│  └──────┬───────────────────────┬───────────────────────┬──────┘  │
│         │                       │                       │         │
└─────────┼───────────────────────┼───────────────────────┼─────────┘
          │ OTLP gRPC             │ Remote Write           │ HTTP Push
          ▼                       ▼                        ▼
┌──────────────┐       ┌──────────────────┐       ┌──────────────┐
│    Jaeger    │       │   Prometheus     │       │    Loki      │
│  (Traces)    │       │   (Métriques)   │       │   (Logs)     │
│  :4317       │       │   :9090          │       │  :3100       │
└──────────────┘       └──────────────────┘       └──────────────┘
       │                        │                        │
       └────────────────────────┴────────────────────────┘
                                │
                                ▼
                        ┌───────────────┐
                        │    Grafana    │
                        │  (Dashboard)  │
                        └───────────────┘
```

## Flux de données

| Signal   | Source                             | Via                        | Destination    |
|----------|------------------------------------|----------------------------|----------------|
| Traces   | Flask (auto-instrumentation OTLP)  | OTEL Agent → otlp/jaeger   | Jaeger         |
| Métriques| Flask (OTLP) + hôte EC2 (hostmetrics)| OTEL Agent → prometheusrw | Prometheus     |
| Logs     | Fichier JSON + OTLP                | OTEL Agent → loki          | Loki           |

## Fichiers clés

| Fichier                        | Rôle                                                       |
|--------------------------------|------------------------------------------------------------|
| `dummy-app/app.py`             | Application Flask avec logs JSON structurés                |
| `dummy-app/Dockerfile`         | Build avec `opentelemetry-instrument` comme entrypoint     |
| `dummy-app/requirements.txt`   | Dépendances Flask + OpenTelemetry                          |
| `docker-compose.yml`           | Lancement du conteneur avec variables OTLP                 |
| `otel-collector-config.yaml`   | Config de référence pour le service systemd OTEL           |

## Variables d'environnement (service systemd)

À définir dans `/etc/systemd/system/otel-collector.service` :

```ini
[Service]
Environment="OBSERVABILITY_IP=<IP de l'EC2 Observabilité>"
Environment="JAEGER_IP=<IP de l'EC2 Observabilité>"
```

## Démarrage

```bash
# Sur l'EC2 — recharger la config du collector systemd
sudo systemctl daemon-reload
sudo systemctl restart otel-collector

# Reconstruire et démarrer l'application
docker-compose up -d --build
```
