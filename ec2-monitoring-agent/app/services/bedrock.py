import boto3
import json
import uuid
import logging
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError
from flask import current_app

logger = logging.getLogger(__name__)

# Module-level client cache (reuse across requests — AWS best practice)
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
            retries={
                'max_attempts': max_attempts,
                'mode': 'standard'  # Includes exponential backoff with jitter
            }
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


# System prompt séparé du contexte incident (meilleure structure pour le LLM)
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
        # A lightweight call to test connectivity
        client.meta.service_model
        return {"status": "ok", "message": "Bedrock client initialized"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def generate_diagnosis(incident_context: dict) -> dict:
    """
    Send the incident context to AWS Bedrock and return a structured diagnosis.
    Uses the Converse API (recommended) or Bedrock Agent if configured.
    """
    agent_id = current_app.config.get('BEDROCK_AGENT_ID')
    agent_alias_id = current_app.config.get('BEDROCK_AGENT_ALIAS_ID')

    user_message = f"""Analyze the following incident context and provide a diagnosis.

Incident Context:
{json.dumps(incident_context, indent=2, default=str)}"""

    try:
        if agent_id and agent_alias_id:
            return _invoke_bedrock_agent(agent_id, agent_alias_id, user_message)
        else:
            return _invoke_converse_api(user_message)

    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']

        # Distinguish retryable vs permanent errors for logging
        if error_code in ('ThrottlingException', 'ServiceUnavailableException',
                          'InternalServerException', 'ModelTimeoutException'):
            logger.warning(f"Bedrock transient error (retries exhausted): {error_code} - {error_message}")
        elif error_code in ('ValidationException', 'AccessDeniedException'):
            logger.error(f"Bedrock permanent error: {error_code} - {error_message}")
        else:
            logger.error(f"Bedrock unexpected error: {error_code} - {error_message}")

        return {
            "analysis": f"Bedrock API Error: {error_code}",
            "cause": error_message,
            "repair_command": ""
        }

    except Exception as e:
        logger.error(f"Bedrock invocation failed: {e}")
        return {
            "analysis": f"API Error: {str(e)}",
            "cause": "Service Unavailable",
            "repair_command": ""
        }


def _invoke_converse_api(user_message: str) -> dict:
    """
    Invoke Bedrock using the Converse API (recommended, model-agnostic).
    """
    client = _get_runtime_client()
    model_id = current_app.config.get('BEDROCK_MODEL_ID', 'anthropic.claude-3-haiku-20240307-v1:0')
    max_tokens = current_app.config.get('BEDROCK_MAX_TOKENS', 1024)

    logger.info(f"Invoking Bedrock Converse API with model: {model_id}")

    response = client.converse(
        modelId=model_id,
        system=[{"text": SYSTEM_PROMPT}],
        messages=[
            {
                "role": "user",
                "content": [{"text": user_message}]
            }
        ],
        inferenceConfig={
            "maxTokens": max_tokens,
            "temperature": 0.2  # Low temperature for deterministic diagnostic responses
        }
    )

    # Extract text from Converse API response
    output_message = response.get('output', {}).get('message', {})
    text_response = ""
    for block in output_message.get('content', []):
        if 'text' in block:
            text_response += block['text']

    # Log token usage for cost monitoring
    usage = response.get('usage', {})
    logger.info(f"Bedrock tokens — input: {usage.get('inputTokens', '?')}, output: {usage.get('outputTokens', '?')}")

    return _parse_json_response(text_response)


def _invoke_bedrock_agent(agent_id: str, agent_alias_id: str, user_message: str) -> dict:
    """
    Invoke a dedicated Bedrock Agent (bedrock-agent-runtime).
    """
    client = _get_agent_client()
    session_id = str(uuid.uuid4())

    logger.info(f"Invoking Bedrock Agent: {agent_id} (alias: {agent_alias_id})")

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


def converse_with_tools(model_id: str, system_prompt: str, messages: list, tools: list) -> dict:
    """
    Invoke Bedrock Converse API with tool definitions.
    Used by the agent loop — the model can request tool calls.

    Args:
        model_id: Bedrock model ID
        system_prompt: System prompt defining agent behavior
        messages: Conversation history (list of message dicts)
        tools: List of tool definitions (toolSpec format)

    Returns:
        Raw Bedrock Converse response dict
    """
    client = _get_runtime_client()
    max_tokens = current_app.config.get('BEDROCK_MAX_TOKENS', 1024)

    logger.info(f"Converse with tools — model: {model_id}, messages: {len(messages)}, tools: {len(tools)}")

    response = client.converse(
        modelId=model_id,
        system=[{"text": system_prompt}],
        messages=messages,
        toolConfig={"tools": tools},
        inferenceConfig={
            "maxTokens": max_tokens,
            "temperature": 0.2
        }
    )

    # Log token usage
    usage = response.get('usage', {})
    logger.info(f"Bedrock tokens — input: {usage.get('inputTokens', '?')}, output: {usage.get('outputTokens', '?')}")

    return response


def _parse_json_response(text_response: str) -> dict:
    """Parse the LLM text response into structured JSON."""
    try:
        # Try to extract JSON from the response (LLM might wrap it in markdown)
        clean = text_response.strip()
        if clean.startswith("```"):
            # Remove markdown code fences
            lines = clean.split("\n")
            clean = "\n".join(lines[1:-1])
        return json.loads(clean)
    except json.JSONDecodeError:
        logger.warning("Failed to parse Bedrock JSON response, returning raw text")
        return {
            "analysis": "Failed to parse AI JSON response.",
            "cause": "Unknown",
            "repair_command": "",
            "raw_response": text_response
        }
