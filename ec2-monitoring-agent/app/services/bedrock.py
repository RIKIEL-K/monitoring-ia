import boto3
import json
import uuid
from flask import current_app

def generate_diagnosis(incident_context: dict) -> dict:
    """
    Send the incident context to AWS Bedrock and ask for a structured response:
    - analyse
    - cause
    - commande_reparation
    """
    region = current_app.config.get('AWS_REGION', 'eu-west-1')
    agent_id = current_app.config.get('BEDROCK_AGENT_ID')
    agent_alias_id = current_app.config.get('BEDROCK_AGENT_ALIAS_ID')
    
    prompt = f"""You are an expert SRE (Site Reliability Engineer) diagnosing server incidents.
    Analyze the following incident context (alerts, metrics, logs) and provide a diagnosis.
    
    Incident Context:
    {json.dumps(incident_context, indent=2)}
    
    Provide your response in JSON format with exactly three keys:
    - "analysis": A brief explanation of what is happening.
    - "cause": The root cause based on the logs/metrics.
    - "repair_command": An exact bash command or set of commands to fix the issue.
    """
    
    try:
        if agent_id and agent_alias_id:
            # Invocation d'un AWS Bedrock Agent dédié (bedrock-agent-runtime)
            client = boto3.client('bedrock-agent-runtime', region_name=region)
            session_id = str(uuid.uuid4())
            
            response = client.invoke_agent(
                agentId=agent_id,
                agentAliasId=agent_alias_id,
                sessionId=session_id,
                inputText=prompt
            )
            
            completion = ""
            for event in response.get("completion"):
                chunk = event.get("chunk")
                if chunk:
                    completion += chunk.get("bytes").decode()
            
            text_response = completion
        else:
            # Invocation standard du modèle Claude (bedrock-runtime)
            client = boto3.client('bedrock-runtime', region_name=region)
            model_id = "anthropic.claude-3-haiku-20240307-v1:0"
            
            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 512,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            }
            
            response = client.invoke_model(
                modelId=model_id,
                body=json.dumps(request_body),
                contentType="application/json",
                accept="application/json"
            )
            
            response_body = json.loads(response.get('body').read())
            text_response = response_body.get('content', [{}])[0].get('text', '{}')
        
        # Attempt to parse the JSON from Bedrock response
        try:
            return json.loads(text_response)
        except json.JSONDecodeError:
            return {
                "analysis": "Failed to parse AI JSON response.",
                "cause": "Unknown",
                "repair_command": "",
                "raw_response": text_response
            }
            
    except Exception as e:
        current_app.logger.error(f"Bedrock invocation failed: {e}")
        return {
            "analysis": f"API Error: {str(e)}",
            "cause": "Service Unavailable",
            "repair_command": ""
        }
