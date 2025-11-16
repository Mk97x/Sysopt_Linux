"""
API routes for AI Agent with Bottles integration.
- Ollama streaming & tool calling
- Bottles MCP proxy endpoints
- System scanners (RAM, storage, CVEs, etc.)
- Shortcut creation support
- New: bottles_folder_installer for copying host folders into bottles
"""

import sys, shutil, time, os, subprocess, json, threading, tempfile, traceback, requests, re 
from pathlib import Path
from flask import Blueprint, jsonify, request, Response, stream_with_context, render_template

# Internal scanners
from .scanner.ram_cpu import top_memory_processes
from .scanner.storage import find_largest_files
from .scanner.autorun import list_systemd_enabled, list_user_autostart
from .scanner.ports import scan_ports
from .scanner.cve import check_package_cves

MCP_SERVER_IP = os.getenv("MCP_SERVER_IP", "127.0.0.1")
MCP_SERVER_PORT = os.getenv("MCP_SERVER_PORT", "8766")
MCP_BASE_URL = f"http://{MCP_SERVER_IP}:{MCP_SERVER_PORT}"

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "localhost")
OLLAMA_PORT = os.getenv("OLLAMA_PORT", "11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")

api_routes = Blueprint('api', __name__)

# ------------------------------------------------------------------
# Utility
# ------------------------------------------------------------------
def extract_bottle_name_from_response(response_text: str) -> str | None:
    match = re.search(r"bottle\s*['\"]?([a-zA-Z0-9_\-]{2,32})['\"]?", response_text, re.IGNORECASE)
    return match.group(1) if match else None

# ------------------------------------------------------------------
# Ollama Endpoints 
# ------------------------------------------------------------------
@api_routes.route('/agent/prompt', methods=['POST'])
def agent_prompt():
    data = request.get_json()
    prompt = data.get('prompt')
    if not prompt:
        return jsonify({"error": "prompt required"}), 400
    try:
        url = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/generate"
        payload = {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}
        r = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=600)
        r.raise_for_status()
        answer = r.json().get("response", "")
        return jsonify({"response": answer.strip()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_routes.route('/agent/stream_prompt', methods=['POST'])
def stream_prompt_ollama():
    data = request.get_json()
    prompt = data.get('prompt')
    if not prompt:
        return jsonify({"error": "prompt required"}), 400
    url = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}/v1/chat/completions"
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True
    }
    def generate():
        try:
            with requests.post(url, json=payload, stream=True, timeout=1200) as r:
                if r.status_code != 200:
                    yield f" {json.dumps({'error': f'Ollama request failed: {r.status_code}'})}\n"
                    return
                for line in r.iter_lines():
                    if line and line.startswith(b' '):
                        yield line.decode('utf-8') + "\n"
        except Exception as e:
            yield f" {json.dumps({'error': f'Ollama stream error: {str(e)}'})}\n"
    return Response(stream_with_context(generate()), mimetype="text/event-stream")

# ------------------------------------------------------------------
# System Scanners 
# ------------------------------------------------------------------
@api_routes.route('/scan/ram')
def scan_ram():
    try:
        n = max(1, min(int(request.args.get('n', 10)), 50))
        return jsonify(top_memory_processes(n))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_routes.route('/scan/storage')
def scan_storage():
    try:
        start_path = request.args.get('start_path')
        max_files = max(1, min(int(request.args.get('max_files', 25)), 500))
        files = find_largest_files(start_path=start_path, max_files=max_files)
        return jsonify([{"size": s, "path": p} for s, p in files])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_routes.route('/scan/autorun')
def scan_autorun():
    try:
        return jsonify({
            "systemd": list_systemd_enabled(),
            "user": list_user_autostart()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_routes.route('/scan/ports')
def scan_ports_api():
    try:
        host = request.args.get('host', '127.0.0.1')
        max_port = max(1, min(int(request.args.get('max_port', 1024)), 65535))
        result = scan_ports(host, ports=list(range(1, max_port + 1)))
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_routes.route('/scan/cve')
def scan_cve():
    name = request.args.get('name')
    version = request.args.get('version')
    if not name or not version:
        return jsonify({"error": "name and version required"}), 400
    try:
        return jsonify(check_package_cves(name, version))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ------------------------------------------------------------------
# MCP Proxies
# ------------------------------------------------------------------
BOTTLE_NAME_REGEX = r"^[a-zA-Z0-9_\- \.']{2,32}$"

@api_routes.route('/agent/status/<bottle_name>')
def agent_status(bottle_name):
    if not re.match(BOTTLE_NAME_REGEX, bottle_name):
        return jsonify({"error": "Invalid bottle name"}), 400
    try:
        resp = requests.get(f"{MCP_BASE_URL}/status/{bottle_name}", timeout=5)
        if resp.status_code == 200:
            return jsonify(resp.json())
        return jsonify({"error": f"MCP returned {resp.status_code}"}), resp.status_code
    except Exception as e:
        return jsonify({"error": f"Status check failed: {str(e)}"}), 500

@api_routes.route('/agent/candidates/<bottle_name>')
def agent_candidates(bottle_name):
    if not re.match(BOTTLE_NAME_REGEX, bottle_name):
        return jsonify({"error": "Invalid bottle name"}), 400
    try:
        resp = requests.get(f"{MCP_BASE_URL}/candidates/{bottle_name}", timeout=10)
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_routes.route('/agent/choose_exe', methods=['POST'])
def agent_choose_exe():
    try:
        data = request.get_json()
        bottle = data.get('bottle')
        exe_path = data.get('exe_path')
        if not bottle or not exe_path:
            return jsonify({"error": "Missing bottle or exe_path"}), 400
        resp = requests.post(f"{MCP_BASE_URL}/agent/choose_exe", json=data, timeout=10)
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500





# ------------------------------------------------------------------
# LLM + MCP Streaming Workflow 
# ------------------------------------------------------------------
@api_routes.route('/agent/llm_mcp_stream', methods=['POST'])
def agent_llm_mcp_stream():
    data = request.get_json()
    user_prompt = data.get('prompt')
    if not user_prompt:
        return jsonify({"error": "prompt required"}), 400

    ollama_prompt = f"""
    The user wants to perform an action related to software installation using a Bottles-based system.
    User request: {user_prompt}
    """

    available_tools = [
        {
            "type": "function",
            "function": {
                "name": "bottles_installer",
                "description": "Full installation using Bottles (EXE or ISO).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "program_path": {"type": "string"},
                        "bottle_name": {"type": "string"}
                    },
                    "required": ["program_path", "bottle_name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "bottles_folder_installer",
                "description": "Copies a host folder into a new or existing bottle, scans for EXEs, and prepares candidates for dependency installation and shortcut creation. Use this for pre-extracted games or folders.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "host_folder": {"type": "string", "description": "Absolute path to the folder on the host (e.g., '/mnt/data/PROJEKT/Game')"},
                        "bottle_name": {"type": "string", "description": "Name of the bottle to create or use"},
                        "target_subdir": {"type": "string", "description": "Optional subdirectory inside drive_c (defaults to folder name)"}
                    },
                    "required": ["host_folder", "bottle_name"]
                }
            }
        }
    ]

    ollama_url = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}/v1/chat/completions"
    ollama_payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": ollama_prompt}],
        "tools": available_tools,
        "tool_choice": "auto",
        "stream": True
    }

    def generate():
        try:
            with requests.post(ollama_url, json=ollama_payload, stream=True, timeout=1200) as ollama_resp:
                if ollama_resp.status_code != 200:
                    yield f" {json.dumps({'log': f'Ollama error: {ollama_resp.status_code}'})}\n"
                    return

                for line in ollama_resp.iter_lines():
                    if not line:
                        continue
                    try:
                        decoded = line.decode('utf-8')
                        if decoded.startswith('data: '):
                            json_part = decoded[6:].strip()
                            if json_part in ('', '[DONE]'):
                                continue

                            data = json.loads(json_part)
                            delta = data.get('choices', [{}])[0].get('delta', {})
                            finish_reason = data.get('choices', [{}])[0].get('finish_reason')

                            # Handle tool call in 'content' 
                            content = delta.get('content', '')
                            if '"function":' in content or '"type":"function"' in content:
                                match = re.search(r'\{"type":"function","function":\{.*?\}\}', content)
                                if match:
                                    func_data = json.loads(match.group(0))["function"]
                                    yield f" {json.dumps({'log': f'[LLM] Tool call detected: {func_data}'})}\n"
                                    mcp_payload = {
                                        "jsonrpc": "2.0",
                                        "method": "tools/call",
                                        "params": func_data,
                                        "id": f"toolcall_{int(time.time())}"
                                    }
                                    try:
                                        mcp_resp = requests.post(MCP_BASE_URL, json=mcp_payload, timeout=10)
                                        if mcp_resp.status_code == 200:
                                            result = mcp_resp.json()
                                            yield f" {json.dumps({'log': f'[MCP] Result: {result}'})}\n"
                                        else:
                                            yield f" {json.dumps({'log': f'[MCP] Error: {mcp_resp.status_code}'})}\n"
                                    except Exception as e2:
                                        yield f" {json.dumps({'log': f'[MCP] Connection error: {e2}'})}\n"

                            # Handle legacy 'tool_calls' delta
                            elif 'tool_calls' in delta:
                                for tc in delta['tool_calls']:
                                    func = tc.get('function', {})
                                    if 'name' in func and 'arguments' in func:
                                        try:
                                            args = json.loads(func.get('arguments', '{}'))
                                            tool_call = {"name": func['name'], "arguments": args}
                                            yield f" {json.dumps({'log': f'[LLM] Legacy tool call: {tool_call}'})}\n"
                                            mcp_payload = {
                                                "jsonrpc": "2.0",
                                                "method": "tools/call",
                                                "params": tool_call,
                                                "id": f"legacy_{int(time.time())}"
                                            }
                                            mcp_resp = requests.post(MCP_BASE_URL, json=mcp_payload, timeout=10)
                                            if mcp_resp.status_code == 200:
                                                yield f" {json.dumps({'log': f'[MCP] Result: {mcp_resp.json()}'})}\n"
                                        except Exception as e3:
                                            yield f" {json.dumps({'log': f'[LLM] Parse error: {e3}'})}\n"

                    except Exception as e_inner:
                        yield f" {json.dumps({'log': f'[Stream error]: {e_inner}'})}\n"
                        continue

        except Exception as e_outer:
            yield f" {json.dumps({'log': f'[Critical error]: {e_outer}'})}\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")
