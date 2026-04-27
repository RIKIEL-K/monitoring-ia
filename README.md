# 📊 Monitoring IA — AIOps avec Machine Learning

Un **agent IA autonome** qui monitore des serveurs sur AWS EC2 en utilisant **AWS Bedrock** (Claude) avec **Tool Use**.

> **IsolationForest** détecte les anomalies CPU en temps réel.
> **Prophet** prédit l'évolution des métriques sur 7 jours.

---

## 1. Vue globale — Les 3 EC2

Tout le système repose sur **3 instances EC2** qui communiquent dans le **même VPC AWS** :

```mermaid
flowchart TB
    subgraph VPC[" AWS VPC"]
        subgraph EC2_1["EC2 #1 — Serveur Cible"]
            APP[" Flask App\n:8080"]
            NE["Node Exporter\n:9100"]
            PT[" Promtail"]
            APP -->|"écrit"| LOGS["dummy-app.log"]
            PT -->|"lit"| LOGS
        end

        subgraph EC2_2["EC2 #2 — Observabilité"]
            PROM[" Prometheus\n:9090"]
            LOKI["Loki\n:3100"]
        end
        
        subgraph EC2_3["EC2 #3 — Agent IA"]
            API["🔌 Flask API\n:5000"]
            SCHED["⏰ Scheduler"]
            LOOP["🧠 Agent Loop"]
            TOOLS["🔧 Tools"]
        end
    end

    NE -->|"scrape :9100\n(métriques CPU/RAM/disk)"| PROM
    PT -->|"push :3100\n(logs applicatifs)"| LOKI
    TOOLS -->|"requête PromQL"| PROM
    TOOLS -->|"requête LogQL"| LOKI
    TOOLS -->|"HTTP health check"| APP
    LOOP <-->|"Converse API\n(HTTPS :443)"| BEDROCK["☁️ AWS Bedrock\nClaude"]
    
    style EC2_1 fill:#1a1a2e,stroke:#e94560,color:#fff
    style EC2_2 fill:#1a1a2e,stroke:#0f3460,color:#fff
    style EC2_3 fill:#1a1a2e,stroke:#16c79a,color:#fff
```

| EC2 | Composant | Dossier | Ports |
|---|---|---|---|
| **Serveur Cible** | Dummy App + Node Exporter + Promtail | [ec2-target-app](./ec2-target-app) | 8080, 9100 |
| **Observabilité** | Prometheus + Loki | [ec2-observability](./ec2-observability) | 9090, 3100 |
| **Agent IA** | Flask API + Agent Loop + Scheduler | [ec2-monitoring-agent](./ec2-monitoring-agent) | 5000 |

---

## 2. Comment fonctionne le ML ?

### IsolationForest — Détection d'anomalies

L'algorithme apprend ce qui est **"normal"** à partir de l'historique CPU, puis signale tout ce qui dévie.

```mermaid
flowchart LR
    A["train_model.py\n(1x/jour à 3h)"] -->|"crée"| M["anomaly_model.pkl"]
    M -->|"chargé par"| B["detect_anomalie.py\n(toutes les 5 min)"]
    P["Prometheus"] -->|"CPU metrics"| A
    P -->|"CPU metrics"| B
    B -->|"log"| L["/var/log/ml/detect.log"]
```

**Problèmes** : le LLM reçoit des données qu'il n'a pas demandées, le code décide quoi collecter, pas d'investigation.

#### ✅ Agent IA (notre système)

```mermaid
flowchart LR
    B1["Cycle déclenché"] --> B2["Agent DÉCIDE\nquoi investiguer"]
    B2 --> B3["Appelle un outil"]
    B3 --> B4["Reçoit les résultats"]
    B4 --> B2
    B2 -->|"assez d'info"| B5["Diagnostic final"]
```

**Métriques prédites** :
| Métrique | Query PromQL | Seuil d'alerte |
|---|---|---|
| **Qui décide quoi investiguer ?** | Le code (hardcodé) | Le LLM (autonome) |
| **Monitoring** | Réactif (attend une alerte) | Proactif (scheduler) |
| **Outils** | Tout en bloc | Appelés à la demande |
| **Investigation** | 1 appel LLM | Boucle multi-itérations |
| **Adaptabilité** | Requêtes fixes | S'adapte au contexte |
| **Historique** | Aucun | Incidents sauvegardés |

---

## 3. La boucle agent en détail

Voici exactement ce qui se passe à chaque cycle de monitoring :

```mermaid
sequenceDiagram
    participant S as ⏰ Scheduler
    participant L as 🧠 Agent Loop
    participant B as ☁️ Bedrock Claude
    participant T as 🔧 Tools
    participant P as 📈 Prometheus
    participant K as 📝 Loki
    participant A as 🌐 Target App

    S->>L: Déclenche un cycle
    L->>B: Prompt: "Vérifie l'état du système"<br/>+ 4 tool definitions
    
    Note over B: L'agent RÉFLÉCHIT:<br/>"Commençons par un overview"
    B->>L: toolUse: get_system_overview()
    L->>T: Exécute get_system_overview
    T->>P: PromQL: node_cpu, node_memory, etc.
    P-->>T: Résultats métriques
    T-->>L: {cpu: 92%, ram: 340MB free}
    L->>B: toolResult: {cpu: 92%, ram: 340MB}
    
    Note over B: L'agent RÉFLÉCHIT:<br/>"CPU à 92% — c'est élevé,<br/>regardons les logs"
    B->>L: toolUse: query_loki({query: "error"})
    L->>T: Exécute query_loki
    T->>K: LogQL query
    K-->>T: 15 lignes de logs
    T-->>L: {logs: ["DatabaseConnectionError..."]}
    L->>B: toolResult: {15 error logs}
    
    Note over B: L'agent RÉFLÉCHIT:<br/>"Des erreurs DB,<br/>vérifions l'app"
    B->>L: toolUse: check_service_health(/health)
    L->>T: Exécute check_health
    T->>A: GET /api/health
    A-->>T: 200 OK (0.5s)
    T-->>L: {status: healthy, 0.5s}
    L->>B: toolResult: {healthy}
    
    Note over B: L'agent CONCLUT:<br/>"App OK mais DB errors<br/>+ CPU high → fuite mémoire"
    B-->>L: Diagnostic JSON final
    L->>L: Sauvegarde incident
```

---

## 4. Le mécanisme Bedrock Tool Use

Le cœur technique du système agent repose sur l'API **Converse** de Bedrock avec **toolConfig** :

```mermaid
flowchart TD
    subgraph send["Ce qu'on ENVOIE à Bedrock"]
        M["messages[]\n(historique conversation)"]
        TS["toolConfig.tools[]\n(4 tool definitions)"]
        SYS["system[]\n(prompt SRE)"]
    end
    
    subgraph bedrock["Bedrock Converse API"]
        LLM["Claude réfléchit\net décide"]
    end
    
    subgraph response["Ce que Bedrock RETOURNE"]
        R1["Cas 1: toolUse\n{name, input, toolUseId}"]
        R2["Cas 2: text\n(diagnostic final)"]
    end
    
    send --> bedrock
    bedrock --> response
    
    R1 -->|"On exécute l'outil,\non renvoie le résultat"| send
    R2 -->|"Fin de la boucle"| DONE["📋 Incident Report"]
```

Chaque **tool definition** envoyée à Bedrock ressemble à ça :

```json
{
  "toolSpec": {
    "name": "query_prometheus",
    "description": "Execute a PromQL query...",
    "inputSchema": {
      "json": {
        "type": "object",
        "properties": {
          "query": {"type": "string"}
        },
        "required": ["query"]
      }
    }
  }
}
```

> Claude **lit les descriptions** et **décide** quel outil est pertinent pour sa tâche.

---

## 5. Le flux de données complet

```mermaid
flowchart LR
    subgraph data_in["Données Entrantes"]
        D1["CPU/RAM/Disk\n(node-exporter)"]
        D2["Logs applicatifs\n(Promtail)"]
    end
    
    subgraph storage["Stockage"]
        S1["Prometheus\n(métriques TSDB)"]
        S2["Loki\n(logs indexés)"]
    end
    
    subgraph agent["Agent IA"]
        direction TB
        A1["Scheduler\n(toutes les 5 min)"]
        A2["Boucle Agent"]
        A3["Tools"]
        A4["Bedrock Claude"]
        A1 --> A2
        A2 <--> A4
        A4 -.->|"toolUse"| A3
        A3 -.->|"résultats"| A2
    end
    
    subgraph output["Sortie"]
        O1["📋 Incidents\n(GET /incidents)"]
        O2["📊 API Status\n(GET /status)"]
    end
    
    D1 --> S1
    D2 --> S2
    A3 --> S1
    A3 --> S2
    A2 --> O1
    agent --> O2
```

---

## 6. Exemple concret : Scénario de crash DB

### Étape 1 — Le problème se produit
L'application web essaie de se connecter à la DB mais elle est down. Des logs d'erreur sont écrits :
```
2026-03-28 02:30:00 - ERROR - DatabaseConnectionError: impossible de se connecter (timeout)
2026-03-28 02:30:05 - ERROR - DatabaseConnectionError: impossible de se connecter (timeout)
2026-03-28 02:30:10 - ERROR - DatabaseConnectionError: impossible de se connecter (timeout)
```

### Étape 2 — Les données circulent
- **Promtail** lit les nouveaux logs → les pousse vers **Loki** (EC2 Observabilité)
- **Prometheus** scrape node-exporter → détecte que le CPU est à 95%

### Étape 3 — L'agent se déclenche
Le **scheduler** (toutes les 5 min) déclenche un cycle. L'agent envoie à Bedrock :
> *"Vérifie l'état du système"* + les 4 tool definitions

### Étape 4 — L'agent investigue lui-même
Claude **décide** la séquence d'investigation :

1. `get_system_overview()` → CPU: 95%, RAM: 80MB libre
2. `query_loki({query: '{job="dummy_web_app"} |= "error"'})` → 47 lignes "DatabaseConnectionError"
3. `check_service_health("http://10.0.1.5:8080/api/health")` → 200 OK mais 2.3s de latence

### Étape 5 — L'agent conclut
Claude produit son diagnostic final :
```json
{
  "severity": "critical",
  "analysis": "Le serveur de base de données à 10.0.0.5 est injoignable, causant des timeouts répétés. Le CPU élevé est dû aux tentatives de reconnexion en boucle.",
  "cause": "Instance DB down ou réseau coupé vers 10.0.0.5",
  "repair_command": "sudo systemctl restart postgresql && sudo systemctl status postgresql",
  "metrics_checked": ["cpu_usage", "memory_available", "app_logs", "service_health"]
}
```
Ce rapport est sauvegardé et accessible via `GET /api/v1/incidents`.

---

## Prérequis AWS

### VPC
Les 3 EC2 doivent être dans le **même VPC**. Utiliser les **IPs privées** pour la communication.

---

## 5. Déploiement

### 5.1 EC2 Target App
```bash
cd ec2-target-app
docker-compose up -d
```

### 5.2 EC2 Observabilité
```bash
cd ec2-observability
# Éditer prometheus.yml avec l'IP privée de l'EC2 Target
docker-compose up -d
```

### 5.3 EC2 Agent ML

```bash
# Installer Python + dépendances système
sudo apt install -y python3 python3-pip python3-dev gcc g++

# Cloner le projet
cd ~
git clone <URL_REPO> monitoring-ia

# Installer les packages Python
cd ~/monitoring-ia/ML
pip3 install --user -r requirements.txt

# Installer cmdstan (moteur de calcul pour Prophet)
python3 -c "import cmdstanpy; cmdstanpy.install_cmdstan()"

# Configurer le .env
cp .env.example .env
nano .env
# → Remplacer l'IP par celle de votre EC2 Observabilité

# Créer le dossier de logs
sudo mkdir -p /var/log/ml
sudo chown ubuntu:ubuntu /var/log/ml

# Créer les dossiers de modèles
mkdir -p ~/monitoring-ia/ML/models/prophet
```

### 5.4 Test manuel (dans l'ordre)

```bash
# IsolationForest
cd ~/monitoring-ia/ML
python3 train_model.py         # entraîne le modèle
python3 detect_anomalie.py     # teste la détection

# Prophet
cd ~/monitoring-ia/ML/ML_Prophet
python3 train_forcasting_model.py   # entraîne les 3 modèles
python3 forecast_metrics.py         # génère les prédictions
```

### 5.5 Activer les cron jobs

```bash
crontab -e
# Coller le contenu de ML/ML_Prophet/cron.txt (adapter l'IP)
# Vérifier : crontab -l
```

---

## 6. Vérification

```bash
# Vérifier la connectivité
curl http://<IP_AGENT>:5000/api/v1/status

# Démarrer le monitoring proactif
curl -X POST http://<IP_AGENT>:5000/api/v1/agent/start

# Arrêter le monitoring
curl -X POST http://<IP_AGENT>:5000/api/v1/agent/stop

# Forcer un cycle immédiat
curl -X POST http://<IP_AGENT>:5000/api/v1/agent/run-now
```

### Incidents
```bash
cd ~/monitoring-ia/ML
python3 detect_anomalie.py
# → Doit afficher : ⚠️ ANOMALIES DETECTED!
```

---

## Outils de l'Agent

L'agent dispose de 4 outils qu'il peut appeler **à sa discrétion** :

| Outil | Description |
|---|---|
| `query_prometheus` | Exécute une requête PromQL (CPU, RAM, disk...) |
| `query_loki` | Recherche dans les logs applicatifs (erreurs, warnings...) |
| `check_service_health` | Vérifie si un endpoint HTTP répond |
| `get_system_overview` | Snapshot complet du système (CPU, RAM, disk, load) |

---

