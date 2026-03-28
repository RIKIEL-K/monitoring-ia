"""
Agent Loop — Boucle autonome de l'agent IA utilisant Bedrock Converse API avec Tool Use.

L'agent décide quels outils appeler et dans quel ordre pour investiguer le système.
La boucle continue jusqu'à ce que le modèle retourne un diagnostic final (texte).
"""
import json
import logging
from datetime import datetime, timezone

from app.agent.tools import TOOL_DEFINITIONS, execute_tool

logger = logging.getLogger(__name__)

# In-memory incident history (list of dicts)
_incident_history = []

# System prompt that defines the agent's behavior
AGENT_SYSTEM_PROMPT = """You are an autonomous SRE (Site Reliability Engineer) agent monitoring servers in production.

Your job is to proactively check the health of the system using the tools available to you.
You MUST call tools to investigate — do NOT guess or assume anything.

## Your investigation strategy:
1. Start with get_system_overview to get a quick snapshot of CPU, memory, disk
2. If any metric looks abnormal (high CPU, low memory, low disk), investigate further
3. Check application health with check_service_health
4. If you find issues, query logs with query_loki to find error details
5. Use query_prometheus for specific metrics if needed

## Your response format:
When you have gathered enough information, provide your final assessment as a JSON object:
{
    "severity": "ok" | "warning" | "critical",
    "analysis": "What is happening on the system",
    "cause": "Root cause if there is an issue, or 'System healthy' if everything is fine",
    "repair_command": "Bash command to fix the issue, or empty string if no action needed",
    "metrics_checked": ["list of metrics you verified"]
}

IMPORTANT: Always base your diagnosis on REAL data from the tools. Never fabricate data."""


def run_agent_cycle(app) -> dict:
    """
    Execute one full agent monitoring cycle.
    
    Args:
        app: Flask application instance (needed for app context)
    
    Returns:
        dict with the cycle result and agent's diagnosis
    """
    with app.app_context():
        from app.services.bedrock import converse_with_tools

        max_iterations = app.config.get('AGENT_MAX_ITERATIONS', 10)
        model_id = app.config.get('BEDROCK_MODEL_ID', 'anthropic.claude-3-haiku-20240307-v1:0')

        cycle_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        logger.info(f"=== Agent Cycle {cycle_id} START ===")

        # Initial prompt for the agent
        initial_message = (
            "A routine monitoring check has been triggered. "
            "Use your tools to verify the health of all monitored systems. "
            "Investigate any anomalies you find."
        )

        # Build the conversation with tool use loop
        messages = [
            {
                "role": "user",
                "content": [{"text": initial_message}]
            }
        ]

        tool_calls_log = []

        for iteration in range(max_iterations):
            logger.info(f"--- Agent iteration {iteration + 1}/{max_iterations} ---")

            # Call Bedrock Converse with tools
            try:
                response = converse_with_tools(
                    model_id=model_id,
                    system_prompt=AGENT_SYSTEM_PROMPT,
                    messages=messages,
                    tools=TOOL_DEFINITIONS
                )
            except Exception as e:
                logger.error(f"Bedrock call failed at iteration {iteration + 1}: {e}")
                result = _create_error_result(cycle_id, str(e), tool_calls_log)
                _incident_history.append(result)
                return result

            # Extract the assistant's response
            response_message = response.get("output", {}).get("message", {})
            stop_reason = response.get("stopReason", "")
            messages.append(response_message)

            # Check if the model wants to use tools
            tool_requests = [
                block for block in response_message.get("content", [])
                if "toolUse" in block
            ]

            if not tool_requests:
                # No tool calls = final text response from the agent
                text_content = ""
                for block in response_message.get("content", []):
                    if "text" in block:
                        text_content += block["text"]

                logger.info(f"Agent produced final response at iteration {iteration + 1}")
                result = _process_final_response(cycle_id, text_content, tool_calls_log)
                _incident_history.append(result)
                logger.info(f"=== Agent Cycle {cycle_id} END — severity: {result.get('severity', 'unknown')} ===")
                return result

            # Execute each tool the agent requested
            tool_results_content = []
            for tool_request in tool_requests:
                tool_use = tool_request["toolUse"]
                tool_name = tool_use["name"]
                tool_input = tool_use.get("input", {})
                tool_use_id = tool_use["toolUseId"]

                logger.info(f"Agent called tool: {tool_name}({json.dumps(tool_input, default=str)[:200]})")

                # Execute the tool
                tool_result = execute_tool(tool_name, tool_input)

                tool_calls_log.append({
                    "iteration": iteration + 1,
                    "tool": tool_name,
                    "input": tool_input,
                    "result_summary": _summarize_result(tool_result)
                })

                # Format tool result for Bedrock
                tool_results_content.append({
                    "toolResult": {
                        "toolUseId": tool_use_id,
                        "content": [{"json": tool_result}]
                    }
                })

            # Append tool results as the "user" role (Bedrock convention)
            messages.append({
                "role": "user",
                "content": tool_results_content
            })

        # Max iterations reached
        logger.warning(f"Agent cycle {cycle_id} reached max iterations ({max_iterations})")
        result = _create_error_result(
            cycle_id,
            f"Max iterations ({max_iterations}) reached without final diagnosis",
            tool_calls_log
        )
        _incident_history.append(result)
        return result


def _process_final_response(cycle_id: str, text_response: str, tool_calls_log: list) -> dict:
    """Parse the agent's final text response into a structured incident report."""
    try:
        # Try to extract JSON from the response
        clean = text_response.strip()
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
            clean = "\n".join(json_lines)

        diagnosis = json.loads(clean)
    except json.JSONDecodeError:
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
        "tool_calls": tool_calls_log,
        "iterations": len(tool_calls_log)
    }


def _create_error_result(cycle_id: str, error: str, tool_calls_log: list) -> dict:
    """Create an error result when the agent cycle fails."""
    return {
        "cycle_id": cycle_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "severity": "error",
        "diagnosis": {
            "analysis": f"Agent cycle failed: {error}",
            "cause": "Agent error",
            "repair_command": ""
        },
        "tool_calls": tool_calls_log,
        "iterations": len(tool_calls_log)
    }


def _summarize_result(result: dict) -> str:
    """Create a short summary of a tool result for logging."""
    status = result.get("status", "unknown")
    if "error" in result:
        return f"error: {result['error'][:100]}"
    if "log_count" in result:
        return f"{status}: {result['log_count']} logs"
    if "result_count" in result:
        return f"{status}: {result['result_count']} results"
    if "http_status" in result:
        return f"{status}: HTTP {result['http_status']}"
    return status


def get_incident_history(limit: int = 50) -> list:
    """Return the most recent incidents."""
    return list(reversed(_incident_history[-limit:]))


def clear_incident_history():
    """Clear the incident history."""
    _incident_history.clear()
