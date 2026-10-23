"""Run inside Azure with the API UAMI; never print or persist bearer tokens."""

import json
import os
import time
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from azure.identity import ManagedIdentityCredential


def main():
    endpoint = os.environ["CHAT_MODEL_BASE_URL"].rstrip("/")
    deployment = os.environ.get("CHAT_MODEL_DEPLOYMENT", "instruct-chat-luna")
    credential = ManagedIdentityCredential(client_id=os.environ["AZURE_CLIENT_ID"])

    def respond(body):
        for attempt in range(4):
            token = credential.get_token("https://cognitiveservices.azure.com/.default").token
            request = Request(
                endpoint + "/responses",
                data=json.dumps({
                    "model": deployment,
                    "max_output_tokens": 1400,
                    "reasoning": {"effort": "low"},
                    "store": False,
                    "instructions": "Be a concise, helpful general classroom assistant.",
                    **body,
                }).encode(),
                headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
            )
            try:
                with urlopen(request, timeout=45) as response:
                    return json.load(response)
            except HTTPError as error:
                if error.code != 429 or attempt == 3:
                    detail = error.read().decode()[:1000]
                    raise RuntimeError(f"Model inference HTTP {error.code}: {detail}") from None
                time.sleep(min(30, max(15, int(error.headers.get("retry-after", "15")))))
        raise RuntimeError("Inference retry bound exhausted")

    messages = [{"role": "user", "content": "Use the add_numbers tool to add 2 and 3."}]
    first = respond({
        "input": messages,
        "tools": [{
            "type": "function",
            "name": "add_numbers",
            "description": "Add two integers.",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
                "required": ["a", "b"],
                "additionalProperties": False,
            },
        }],
        "tool_choice": "required",
        "parallel_tool_calls": False,
    })
    call = next(item for item in first["output"] if item["type"] == "function_call")
    arguments = json.loads(call["arguments"])
    assert call["name"] == "add_numbers"
    assert arguments == {"a": 2, "b": 3}
    messages.extend(first["output"])
    messages.extend([
        {"type": "function_call_output", "call_id": call["call_id"], "output": "5"},
        {"role": "user", "content": "Explain the result briefly in plain conversational prose."},
    ])
    second = respond({"input": messages})
    prose = "".join(
        content["text"]
        for item in second["output"] if item["type"] == "message"
        for content in item["content"] if content["type"] == "output_text"
    )
    assert prose and ("5" in prose or "five" in prose.lower())
    third = respond({
        "input": [{"role": "user", "content": "Return the sum of 2 and 3."}],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "sum_result",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {"sum": {"type": "integer"}},
                    "required": ["sum"],
                    "additionalProperties": False,
                },
            },
        },
    })
    structured = json.loads(next(
        content["text"]
        for item in third["output"] if item["type"] == "message"
        for content in item["content"] if content["type"] == "output_text"
    ))
    assert structured == {"sum": 5}
    print("CHAT_MODEL_VERIFIED " + json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "identityClientId": os.environ["AZURE_CLIENT_ID"],
        "protocol": "OpenAI v1 responses",
        "baseUrl": endpoint + "/",
        "deployment": deployment,
        "responseModel": second["model"],
        "toolCall": {"name": call["name"], "arguments": arguments},
        "prose": prose,
        "structuredOutput": structured,
        "usage": [response.get("usage") for response in (first, second, third)],
        "status": "passed",
    }), flush=True)


if __name__ == "__main__":
    main()
