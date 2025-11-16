from flask import Flask, jsonify, render_template, request, send_from_directory, Response
from flask_cors import CORS
import os
import sys
import json
import shutil
import threading
import time
import subprocess
from pathlib import Path

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from .api import api_routes
from .scanner.ram_cpu import top_memory_processes
from .scanner.storage import find_largest_files
from .scanner.autorun import list_systemd_enabled, list_user_autostart
from .scanner.ports import scan_ports
from .scanner.cve import check_package_cves
from .agent.llm_client import LLMClient

template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'webui', 'templates')
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'webui', 'static')

app = Flask(__name__,
           template_folder=template_dir,
           static_folder=static_dir)

CORS(app)  # Enable CORS for API calls

CORS(app, resources={
    r"/api/*": {"origins": "*"},
    r"/api/agent/stream_prompt": {
        "origins": "*",
        "methods": ["POST"],
        "allow_headers": ["Content-Type"]
    }
})

# Register API routes
app.register_blueprint(api_routes, url_prefix='/api')

# ------------------------------------------------------------------
# SETUP & RESTART LOGIC (moved from api.py to main.py)
# ------------------------------------------------------------------
ENV_FILE_PATH = os.path.abspath(".env")

@app.route('/setup')
def setup_page():
    """Render setup page with current env values."""
    current = {
        "PREFIX": os.getenv("PREFIX", ""),
        "OLLAMA_HOST": os.getenv("OLLAMA_HOST", "localhost"),
        "OLLAMA_PORT": os.getenv("OLLAMA_PORT", "11434"),
        "OLLAMA_MODEL": os.getenv("OLLAMA_MODEL", "llama3.2"),
        "MCP_SERVER_IP": os.getenv("MCP_SERVER_IP", "127.0.0.1"),
        "MCP_SERVER_PORT": os.getenv("MCP_SERVER_PORT", "8766"),
        "WEBUI_PORT": os.getenv("WEBUI_PORT", "8000"),
    }
    return render_template("setup.html", config=current)

@app.route('/save_config_and_start', methods=['POST'])
def save_config_and_start():
    """Save config to .env and restart the current process."""
    try:
        data = request.get_json()
        required_fields = ["PREFIX", "OLLAMA_HOST", "OLLAMA_PORT", "OLLAMA_MODEL",
                           "MCP_SERVER_IP", "MCP_SERVER_PORT", "WEBUI_PORT"]
        for field in required_fields:
            if field not in data or (isinstance(data[field], str) and not data[field].strip()):
                return jsonify({"error": f"Missing or empty field: {field}"}), 400

        # Validate ports
        for port_key in ["OLLAMA_PORT", "MCP_SERVER_PORT", "WEBUI_PORT"]:
            port = int(data[port_key])
            if not (1 <= port <= 65535):
                return jsonify({"error": f"Invalid port: {port_key}"}), 400

        # Write .env
        with open(ENV_FILE_PATH, 'w') as f:
            f.write(f'PREFIX={data["PREFIX"]}\n')
            f.write(f'OLLAMA_HOST={data["OLLAMA_HOST"]}\n')
            f.write(f'OLLAMA_PORT={data["OLLAMA_PORT"]}\n')
            f.write(f'OLLAMA_MODEL={data["OLLAMA_MODEL"]}\n')
            f.write(f'MCP_SERVER_IP={data["MCP_SERVER_IP"]}\n')
            f.write(f'MCP_SERVER_PORT={data["MCP_SERVER_PORT"]}\n')
            f.write(f'WEBUI_PORT={data["WEBUI_PORT"]}\n')

        # Trigger restart
        def _restart():
            time.sleep(0.5)
            subprocess.Popen([sys.executable, '-m', 'app.main'] + sys.argv[2:])
            os._exit(0)


        return jsonify({
            "message": "Configuration saved. Application is restarting..."
        })

    except Exception as e:
        return jsonify({"error": f"Failed to save config: {str(e)}"}), 500

@app.route('/start_mcp', methods=['POST'])
def start_mcp():
    """Startet den MCP-Server als separaten Prozess."""
    try:
        def run_mcp():
            try:
                subprocess.run([sys.executable, '-m', 'mcp.bottles_mcp'], check=True)
            except subprocess.CalledProcessError as e:
                print(f"[ERROR] MCP failed to start: {e}")

        thread = threading.Thread(target=run_mcp)
        thread.daemon = True
        thread.start()

        return jsonify({"status": "started", "message": "MCP server started in background."})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# Serve static files
@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('webui/static', path)

# Web UI Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/scan')
def scan():
    return render_template('scan.html')

@app.route('/agent')
def agent():
    return render_template('agent.html')

# Health check
@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)