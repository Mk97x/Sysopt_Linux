from flask import Blueprint, jsonify, request
from .scanner.ram_cpu import top_memory_processes
from .scanner.storage import find_largest_files
from .scanner.autorun import list_systemd_enabled, list_user_autostart
from .scanner.ports import scan_ports
from .scanner.cve import check_package_cves
from .agent.llm_client import LLMClient

api_routes = Blueprint('api', __name__)

@api_routes.route('/scan/ram')
def scan_ram():
    try:
        n = int(request.args.get('n', 10))
        n = max(1, min(n, 50))  # Clamp between 1 and 50
        result = top_memory_processes(n)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_routes.route('/scan/storage')
def scan_storage():
    try:
        start_path = request.args.get('start_path')
        max_files = int(request.args.get('max_files', 25))
        max_files = max(1, min(max_files, 500))  # Clamp between 1 and 500
        
        files = find_largest_files(start_path=start_path, max_files=max_files)
        result = [{"size": s, "path": p} for s, p in files]
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_routes.route('/scan/autorun')
def scan_autorun():
    try:
        result = {
            "systemd": list_systemd_enabled(),
            "user": list_user_autostart()
        }
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_routes.route('/scan/ports')
def scan_ports_api():
    try:
        host = request.args.get('host', '127.0.0.1')
        max_port = int(request.args.get('max_port', 1024))
        max_port = max(1, min(max_port, 65535))  # Clamp between 1 and 65535
        
        ports = list(range(1, max_port + 1))
        result = scan_ports(host, ports=ports)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_routes.route('/scan/cve')
def scan_cve():
    try:
        name = request.args.get('name')
        version = request.args.get('version')
        
        if not name or not version:
            return jsonify({"error": "name and version parameters required"}), 400
            
        result = check_package_cves(name, version)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_routes.route('/agent/prompt', methods=['POST'])
def agent_prompt():
    """Handles User - Agent communication"""
    try:
        data = request.get_json()
        prompt = data.get('prompt')
        
        if not prompt:
            return jsonify({"error": "prompt required"}), 400
            
        client = LLMClient()
        result = client.run_prompt(prompt)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500