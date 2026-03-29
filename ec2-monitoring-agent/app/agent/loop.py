"""
Agent Loop — Boucle autonome de l'agent IA utilisant Strands Agents + Amazon Bedrock.

Strands gère automatiquement :
  - La boucle toolUse / toolResult
  - La gestion des itérations
  - Le parsing des appels d'outils

On se concentre ici sur :
  - La construction du rapport structuré (incident report)
  - La persistance en mémoire de l'historique des incidents
"""
import json
import logging
import re
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# In-memory incident history
_incident_history = []

AGENT_SYSTEM_PROMPT_TEMPLATE = """You are an autonomous SRE (Site Reliability Engineer) agent monitoring servers in production.

Your job is to proactively check the health of the system using the tools available to you.
You MUST call tools to investigate — do NOT guess or assume anything.

## Service URLs (use these exact URLs with check_service_health):
- Prometheus: {prometheus_url}
- Loki: {loki_url}
- Target app: {target_app_url}

## Your investigation strategy:
1. Start with get_system_overview to get a quick snapshot of CPU, memory, disk
2. If any metric looks abnormal (high CPU, low memory, low disk), investigate further
3. Check application health with check_service_health using the URLs above
4. If you find issues, query logs with query_loki to find error details
5. Use query_prometheus for specific metrics if needed

## Your response format:
Respond ONLY with a raw JSON object (no markdown, no explanation before or after):
{{
    "severity": "ok" | "warning" | "critical",
    "analysis": "What is happening on the system",
    "cause": "Root cause if there is an issue, or 'System healthy' if everything is fine",
    "repair_command": "Bash command to fix the issue, or empty string if no action needed",
    "metrics_checked": ["list of metrics you verified"]
}}

IMPORTANT: Your LAST message must be ONLY the JSON object above. No text before or after it. Never fabricate data."""


def run_agent_cycle(app) -> dict:
    """
    Execute one full agent monitoring cycle using Strands Agents.

    Args:
        app: Flask application instance (needed to read config)

    Returns:
        dict with the cycle result and agent's diagnosis
    """
    from strands import Agent
    from strands.models import BedrockModel
    from app.agent.tools import (
        configure_tools,
        query_prometheus,
        query_loki,
        check_service_health,
        get_system_overview,
    )

    with app.app_context():
        prometheus_url = app.config['PROMETHEUS_URL']
        loki_url = app.config['LOKI_URL']
        target_app_url = app.config.get('TARGET_APP_URL', 'http://localhost:8080')

        # Inject service URLs into tools (replaces current_app.config access)
        configure_tools(
            prometheus_url=prometheus_url,
            loki_url=loki_url,
            request_timeout=app.config.get('REQUEST_TIMEOUT', 10)
        )

        model_id = app.config.get('BEDROCK_MODEL_ID', 'us.anthropic.claude-opus-4-1-20250805-v1:0')
        max_tokens = app.config.get('BEDROCK_MAX_TOKENS', 4096)
        region = app.config.get('AWS_REGION', 'us-east-1')

        cycle_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        logger.info(f"=== Agent Cycle {cycle_id} START (Strands + Bedrock: {model_id}, max_tokens={max_tokens}) ===")

        # Inject real service URLs into the system prompt so the LLM knows them
        system_prompt = AGENT_SYSTEM_PROMPT_TEMPLATE.format(
            prometheus_url=prometheus_url,
            loki_url=loki_url,
            target_app_url=target_app_url,
        )

        # Configure Bedrock as the model provider
        bedrock_model = BedrockModel(
            model_id=model_id,
            region_name=region,
            max_tokens=max_tokens,
            temperature=0.2,
        )

        # Build the Strands agent — tool loop is fully managed by Strands
        agent = Agent(
            model=bedrock_model,
            system_prompt=system_prompt,
            tools=[query_prometheus, query_loki, check_service_health, get_system_overview],
        )

        try:
            response = agent(
                "A routine monitoring check has been triggered. "
                "Use your tools to verify the health of all monitored systems. "
                "Investigate any anomalies you find."
            )

            # response is a Strands AgentResult; its string representation is the final text
            final_text = str(response)
            logger.info(f"Agent Cycle {cycle_id} — final response received")

            result = _process_final_response(cycle_id, final_text)

        except Exception as e:
            logger.error(f"Agent Cycle {cycle_id} failed: {e}")
            result = _create_error_result(cycle_id, str(e))

        _incident_history.append(result)
        logger.info(f"=== Agent Cycle {cycle_id} END — severity: {result.get('severity', 'unknown')} ===")
        return result


def _process_final_response(cycle_id: str, text_response: str) -> dict:
    """Parse the agent's final text response into a structured incident report.

    Handles 3 formats:
    1. Pure JSON string
    2. JSON inside a ```json ... ``` code block
    3. Free text followed by a JSON object (e.g. 'Here is my assessment: {...}')
    """
    diagnosis = None
    clean = text_response.strip()

    # Strategy 1: JSON inside a markdown code block
    if "```" in clean:
        lines = clean.split("\n")
        json_lines = []
        in_block = False
        for line in lines:
            if line.strip().startswith("```"):
                in_block = not in_block
                continue
            if in_block:
                json_lines.append(line)
        candidate = "\n".join(json_lines).strip()
        try:
            diagnosis = json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # Strategy 2: Pure JSON
    if diagnosis is None:
        try:
            diagnosis = json.loads(clean)
        except json.JSONDecodeError:
            pass

    # Strategy 3: Extract the first {...} block from mixed text (e.g. "Here is my assessment: {...}")
    if diagnosis is None:
        match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', clean, re.DOTALL)
        if match:
            try:
                diagnosis = json.loads(match.group())
            except json.JSONDecodeError:
                pass

    if diagnosis is None:
        logger.warning(f"Cycle {cycle_id}: could not parse LLM response as JSON. Raw: {clean[:300]}")
        diagnosis = {
            "severity": "unknown",
            "analysis": text_response[:500],
            "cause": "Could not parse structured response",
            "repair_command": "",
        }

    return {
        "cycle_id": cycle_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "severity": diagnosis.get("severity", "unknown"),
        "diagnosis": diagnosis,
    }


def _create_error_result(cycle_id: str, error: str) -> dict:
    """Create an error result when the agent cycle fails."""
    return {
        "cycle_id": cycle_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "severity": "error",
        "diagnosis": {
            "analysis": f"Agent cycle failed: {error}",
            "cause": "Agent error",
            "repair_command": "",
        },
    }


def get_incident_history(limit: int = 50) -> list:
    """Return the most recent incidents."""
    return list(reversed(_incident_history[-limit:]))


def clear_incident_history():
    """Clear the incident history."""
    _incident_history.clear()
