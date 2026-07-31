#!/usr/bin/env python3
"""Forge MCP server — exposes Forge as callable tools rather than prose.

A skill describing Forge lost tool selection twice against 66 builtin skills:
a skill is text competing for the model's attention, while an MCP tool is a
named function with a schema. Weaker models pick functions far more reliably
than they follow instructions, which is the whole reason this exists.

stdio JSON-RPC, standard library only — nothing to install into the agent
image, and no dependency that can break its build.

Register with:
    hermes mcp add --transport stdio forge -- python3 /app/forge_mcp.py

Environment:
    FORGE_API_URL   orchestrator base URL
    FORGE_TOKEN     shared secret; sent as X-Forge-Token
"""

import json
import os
import sys
import urllib.error
import urllib.request

PROTOCOL_VERSION = "2024-11-05"
TIMEOUT = 30

API_URL = os.environ.get("FORGE_API_URL", "").rstrip("/")
TOKEN = os.environ.get("FORGE_TOKEN", "")

TOOLS = [
    {
        "name": "forge_submit_task",
        "description": (
            "Submit a coding task to Forge. Use this for ANY request to build, "
            "add, create, write, change, update, fix, refactor, or review code "
            "in a GitHub repository. Forge clones the repository, edits it with "
            "an AI coding agent, commits, and pushes a branch. Do NOT clone the "
            "repository yourself and do NOT use git or gh — the repositories are "
            "private and this machine has no GitHub credential. Returns a "
            "task_id; poll it with forge_task_status."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repository": {
                    "type": "string",
                    "description": "Repository as owner/name, e.g. HemangVora/forge-worker-runtime",
                },
                "prompt": {
                    "type": "string",
                    "description": (
                        "The user's request, in full. Do not summarize it — detail "
                        "you drop is detail the coding agent cannot act on."
                    ),
                },
            },
            "required": ["repository", "prompt"],
        },
    },
    {
        "name": "forge_task_status",
        "description": (
            "Get a Forge task's current status: queued, running, done, failed, or "
            "cancelled. Work takes minutes — poll roughly every 20 seconds and tell "
            "the user what stage it is at rather than waiting silently. "
            "IMPORTANT: branch is null until status is done, because the branch is "
            "pushed in the final publishing stage. A null branch while status is "
            "running means the work is still in progress — it does NOT mean the "
            "push failed. Never report a failure until status is failed."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
        },
    },
    {
        "name": "forge_task_events",
        "description": (
            "Get the full progress history for a Forge task: preparing, workspace, "
            "profiling, executing, publishing, collecting, done. Use this to explain "
            "what happened, especially when a task failed."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
        },
    },
]


def call_forge(method: str, path: str, payload: dict | None = None) -> dict:
    """One HTTP call to the orchestrator, with failures returned as data.

    A raised exception would surface to the model as an opaque tool error; a
    structured message lets it explain the problem to the user or correct the
    call itself.
    """
    if not API_URL:
        return {"error": "FORGE_API_URL is not set on this machine."}
    if not TOKEN:
        return {"error": "FORGE_TOKEN is not set; Forge rejects unauthenticated calls."}

    body = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        f"{API_URL}{path}",
        data=body,
        method=method,
        headers={"Content-Type": "application/json", "X-Forge-Token": TOKEN},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        if exc.code == 401:
            return {"error": "Forge rejected the token (401). FORGE_TOKEN is wrong."}
        if exc.code == 404:
            return {"error": f"Not found (404): {detail}"}
        return {"error": f"Forge returned HTTP {exc.code}: {detail}"}
    except urllib.error.URLError as exc:
        return {"error": f"Cannot reach Forge at {API_URL}: {exc.reason}"}
    except json.JSONDecodeError:
        return {"error": "Forge returned a response that was not JSON."}


def run_tool(name: str, args: dict) -> dict:
    if name == "forge_submit_task":
        repository = (args.get("repository") or "").strip()
        prompt = (args.get("prompt") or "").strip()
        if "/" not in repository:
            return {
                "error": (
                    f"repository must be owner/name, got {repository!r}. "
                    "Ask the user which repository if they did not say."
                )
            }
        if not prompt:
            return {"error": "prompt is empty — pass the user's request through."}
        result = call_forge("POST", "/task", {"repository": repository, "prompt": prompt})
        if "task_id" in result:
            result["next"] = (
                "Tell the user the task id now, then poll forge_task_status "
                "every ~20 seconds. This takes minutes."
            )
        return result

    if name in ("forge_task_status", "forge_task_events"):
        task_id = (args.get("task_id") or "").strip()
        if not task_id:
            return {"error": "task_id is required."}
        suffix = "/events" if name == "forge_task_events" else ""
        result = call_forge("GET", f"/tasks/{task_id}{suffix}")
        if isinstance(result, list):
            return {"events": result}
        # Say plainly what a null branch means, so a mid-run poll is not read
        # as a failed push.
        if isinstance(result, dict) and result.get("status") == "running":
            result["note"] = (
                "Still running. branch is populated only when status becomes "
                "done — its absence now is expected, not a failure."
            )
        return result

    return {"error": f"Unknown tool: {name}"}


def respond(request_id, result=None, error=None) -> None:
    message = {"jsonrpc": "2.0", "id": request_id}
    if error is not None:
        message["error"] = error
    else:
        message["result"] = result
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = message.get("method")
        request_id = message.get("id")

        if method == "initialize":
            respond(
                request_id,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "forge", "version": "1.0.0"},
                },
            )
        elif method == "tools/list":
            respond(request_id, {"tools": TOOLS})
        elif method == "tools/call":
            params = message.get("params") or {}
            output = run_tool(params.get("name", ""), params.get("arguments") or {})
            respond(
                request_id,
                {"content": [{"type": "text", "text": json.dumps(output, indent=2)}]},
            )
        elif request_id is not None:
            # Notifications carry no id and need no reply.
            respond(request_id, error={"code": -32601, "message": f"Unknown: {method}"})


if __name__ == "__main__":
    main()
