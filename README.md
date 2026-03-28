# Comment des Agents IA peuvent monitorer des serveurs

## Le Principe Général

Un système de monitoring par agents IA repose sur **3 couches** qui communiquent entre elles :

```mermaid
flowchart LR
    A["🖥️ Serveur Cible"] -->|métriques| B["📊 Couche Observabilité"]
    A -->|logs| B
    B -->|alerte| C["🤖 Agent IA"]
    C -->|diagnostic + commande| D["👨‍💻 Équipe SRE"]
    C -->|requête contexte| B
```

Ce projet implémente exactement ce pattern avec 3 composants déployés sur EC2 :

| Composant | Rôle | Dossier |
|---|---|---|
| **Serveur Cible** | L'application à surveiller | [ec2-target-app](./ec2-target-app) |
| **Stack Observabilité** | Collecte métriques + logs | [ec2-observability](./ec2-observability) |
| **Agent IA** | Orchestrateur intelligent | [ec2-monitoring-agent](./ec2-monitoring-agent) |

---

## 1. 🖥️ Le Serveur Cible (`ec2-target-app`)

C'est le serveur qu'on surveille. Il expose deux types de données :

### Métriques (chiffres en temps réel)
- **Node Exporter** (port `9100`) : exporte les métriques système (CPU, RAM, disque, réseau)
- **L'app Flask** (port `8080`) : peut exposer des métriques applicatives

### Logs (texte des événements)
- L'app [app.py](./ec2-target-app/dummy-app/app.py) écrit ses logs dans `/app/logs/dummy-app.log`
- **Promtail** lit ce fichier et l'envoie automatiquement vers **Loki**

```mermaid
flowchart TD
    subgraph EC2_Target["EC2 - Serveur Cible"]
        APP["Flask App :8080"] -->|écrit| LOG["dummy-app.log"]
        NE["Node Exporter :9100"]
        PT["Promtail"] -->|lit| LOG
    end
    NE -->|scrape| PROM["Prometheus"]
    PT -->|push| LOKI["Loki"]
```

---

## 2. 📊 La Couche Observabilité (`ec2-observability`)

Deux outils open-source collectent et stockent les données :

| Outil | Type de données | Port | Rôle |
|---|---|---|---|
| **Prometheus** | Métriques (CPU, RAM…) | `9090` | Scrape les métriques toutes les 15s via [prometheus.yml](./ec2-observability/prometheus.yml) |
| **Loki** | Logs (texte) | `3100` | Reçoit les logs poussés par Promtail |

> **💡 Note :** Prometheus **tire** (pull) les métriques, Loki **reçoit** (push) les logs. Deux paradigmes différents.

---

## 3. 🤖 L'Agent IA (`ec2-monitoring-agent`)

C'est le cœur intelligent du système. Voici son flux de traitement :

```mermaid
sequenceDiagram
    participant Alert as Alertmanager
    participant API as Flask API /api/v1/alerts
    participant Orch as Orchestrator
    participant Prom as Prometheus
    participant Loki as Loki
    participant AI as AWS Bedrock (Claude)

    Alert->>API: POST alerte JSON
    API->>Orch: handle_incident(alert_data)
    Orch->>Loki: Récupérer les logs récents du service
    Loki-->>Orch: logs[ ]
    Orch->>Prom: Récupérer les métriques CPU/RAM
    Prom-->>Orch: metrics{ }
    Orch->>AI: Envoyer contexte complet (alerte + logs + métriques)
    AI-->>Orch: { analysis, cause, repair_command }
    Orch-->>API: Réponse structurée
```

### Les 4 modules clés

| Module | Fichier | Rôle |
|---|---|---|
| **Routes API** | [routes.py](./ec2-monitoring-agent/app/api/routes.py) | Reçoit les alertes (`POST /alerts`) et les simulations (`POST /simulate`) |
| **Orchestrateur** | [orchestrator.py](./ec2-monitoring-agent/app/services/orchestrator.py) | Coordonne tout : parse l'alerte → collecte contexte → appelle l'IA |
| **Service Prometheus** | [prometheus.py](./ec2-monitoring-agent/app/services/prometheus.py) | Requête PromQL pour récupérer les métriques récentes |
| **Service Loki** | [loki.py](./ec2-monitoring-agent/app/services/loki.py) | Requête LogQL pour récupérer les logs d'erreur |
| **Service Bedrock** | [bedrock.py](./ec2-monitoring-agent/app/services/bedrock.py) | Envoie le contexte à Claude (AWS Bedrock) et parse la réponse JSON |

---

## Le Flux Complet (exemple concret)

```
1. L'app crash → écrit "DatabaseConnectionError" dans dummy-app.log
2. Promtail détecte le nouveau log → l'envoie à Loki
3. Prometheus scrape node-exporter → détecte CPU à 95%
4. Alertmanager déclenche une alerte → POST /api/v1/alerts
5. L'orchestrateur :
   ├─ Récupère les 20 derniers logs d'erreur depuis Loki
   ├─ Récupère les métriques CPU depuis Prometheus  
   └─ Envoie le tout à AWS Bedrock (Claude)
6. Claude analyse et retourne :
   {
     "analysis": "Le serveur DB est injoignable, causant des timeouts",
     "cause": "L'instance DB à 10.0.0.5 est down",
     "repair_command": "sudo systemctl restart postgresql"
   }
```

---

## Résumé de l'Architecture

```mermaid
flowchart TB
    subgraph target["🖥️ EC2 - Serveur Cible"]
        A1["Flask App"] 
        A2["Node Exporter"]
        A3["Promtail"]
    end
    
    subgraph obs["📊 EC2 - Observabilité"]
        B1["Prometheus"]
        B2["Loki"]
    end
    
    subgraph agent["🤖 EC2 - Agent IA"]
        C1["Flask API"]
        C2["Orchestrateur"]
        C3["Service Bedrock"]
    end
    
    A2 -->|métriques| B1
    A3 -->|logs| B2
    B1 -->|alerte| C1
    C1 --> C2
    C2 -->|query logs| B2
    C2 -->|query metrics| B1
    C2 --> C3
    C3 -->|prompt| D["☁️ AWS Bedrock Claude"]
    D -->|diagnostic JSON| C3
```
