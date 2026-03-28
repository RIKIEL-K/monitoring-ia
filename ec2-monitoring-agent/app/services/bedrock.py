"""
Bedrock Service — Client Amazon Bedrock pour le flow legacy (/alerts).

NOTE: La boucle agentique principale utilise maintenant Strands Agents
(voir app/agent/loop.py). Ce module gère seulement :
  - Le health check Bedrock (GET /api/v1/status)
  - Le flow legacy orchestrateur (POST /api/v1/alerts)
"""
import boto3
import json
import uuid
import logging
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError
from flask import current_app

logger = logging.getLogger(__name__)

# Module-level client cache (AWS best practice)
_bedrock_runtime_client = None
_bedrock_agent_client = None


def _get_runtime_client():
    """Get or create a reusable bedrock-runtime client with retry config."""
    global _bedrock_runtime_client
    if _bedrock_runtime_client is None:
        region = current_app.config.get('AWS_REGION', 'us-east-1')
        max_attempts = current_app.config.get('BEDROCK_RETRY_MAX_ATTEMPTS', 3)
        retry_config = BotoConfig(
            region_name=region,
            retries={'max_attempts': max_attempts, 'mode': 'standard'}
        )
        _bedrock_runtime_client = boto3.client('bedrock-runtime', config=retry_config)
    return _bedrock_runtime_client


def _get_agent_client():
    """Get or create a reusable bedrock-agent-runtime client."""
    global _bedrock_agent_client
    if _bedrock_agent_client is None:
        region = current_app.config.get('AWS_REGION', 'us-east-1')
        _bedrock_agent_client = boto3.client('bedrock-agent-runtime', region_name=region)
    return _bedrock_agent_client


SYSTEM_PROMPT = """You are an expert SRE (Site Reliability Engineer) diagnosing server incidents.
You analyze alerts, application logs, and system metrics to identify root causes and provide repair commands.
Always respond in JSON format with exactly three keys:
- "analysis": A brief explanation of what is happening.
- "cause": The root cause based on the logs/metrics.
- "repair_command": An exact bash command or set of commands to fix the issue.
If data is missing or insufficient, state it clearly in your analysis and provide your best guess."""


def check_bedrock_connectivity() -> dict:
    """Health check: verify Bedrock is reachable."""
    try:
        client = _get_runtime_client()
        client.meta.service_model  # lightweight check
        return {"status": "ok", "message": "Bedrock client initialized"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def generate_diagnosis(incident_context: dict) -> dict:
    """
    Send an incident context to Bedrock and return a structured diagnosis.
    Used by the legacy /alerts flow (orchestrator).
    The main agent loop now uses Strands Agents instead.
    """
    agent_id = current_app.config.get('BEDROCK_AGENT_ID')
    agent_alias_id = current_app.config.get('BEDROCK_AGENT_ALIAS_ID')

    user_message = (
        f"Analyze the following incident context and provide a diagnosis.\n\n"
        f"Incident Context:\n{json.dumps(incident_context, indent=2, default=str)}"
    )

    try:
        if agent_id and agent_alias_id:
            return _invoke_bedrock_agent(agent_id, agent_alias_id, user_message)
        else:
            return _invoke_converse_api(user_message)

    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        logger.error(f"Bedrock ClientError: {error_code} — {error_message}")
        return {"analysis": f"Bedrock Error: {error_code}", "cause": error_message, "repair_command": ""}

    except Exception as e:
        logger.error(f"Bedrock invocation failed: {e}")
        return {"analysis": f"API Error: {str(e)}", "cause": "Service Unavailable", "repair_command": ""}


def _invoke_converse_api(user_message: str) -> dict:
    """Invoke Bedrock Converse API for a single-turn diagnosis (legacy flow)."""
    client = _get_runtime_client()
    model_id = current_app.config.get('BEDROCK_MODEL_ID', 'us.anthropic.claude-3-5-sonnet-20241022-v2:0')
    max_tokens = current_app.config.get('BEDROCK_MAX_TOKENS', 4096)

    logger.info(f"Invoking Bedrock Converse (legacy) — model: {model_id}")
    response = client.converse(
        modelId=model_id,
        system=[{"text": SYSTEM_PROMPT}],
        messages=[{"role": "user", "content": [{"text": user_message}]}],
        inferenceConfig={"maxTokens": max_tokens, "temperature": 0.2}
    )

    output_message = response.get('output', {}).get('message', {})
    text_response = "".join(
        block['text'] for block in output_message.get('content', []) if 'text' in block
    )

    usage = response.get('usage', {})
    logger.info(f"Bedrock tokens — in: {usage.get('inputTokens', '?')}, out: {usage.get('outputTokens', '?')}")
    return _parse_json_response(text_response)


def _invoke_bedrock_agent(agent_id: str, agent_alias_id: str, user_message: str) -> dict:
    """Invoke a dedicated Bedrock Agent (legacy flow)."""
    client = _get_agent_client()
    session_id = str(uuid.uuid4())
    logger.info(f"Invoking Bedrock Agent: {agent_id}")

    response = client.invoke_agent(
        agentId=agent_id,
        agentAliasId=agent_alias_id,
        sessionId=session_id,
        inputText=user_message
    )

    completion = ""
    for event in response.get("completion"):
        chunk = event.get("chunk")
        if chunk:
            completion += chunk.get("bytes").decode()

    return _parse_json_response(completion)


def _parse_json_response(text_response: str) -> dict:
    """Parse the LLM text response into structured JSON."""
    try:
        clean = text_response.strip()
        if clean.startswith("```"):
            lines = clean.split("\n")
            clean = "\n".join(lines[1:-1])
        return json.loads(clean)
    except json.JSONDecodeError:
        logger.warning("Failed to parse Bedrock JSON response")
        return {
            "analysis": "Failed to parse AI JSON response.",
            "cause": "Unknown",
            "repair_command": "",
            "raw_response": text_response
        }
