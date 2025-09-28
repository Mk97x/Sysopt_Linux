from flask import Flask, jsonify, render_template, request, send_from_directory
from flask_cors import CORS
import os
import sys

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

# Register API routes
app.register_blueprint(api_routes, url_prefix='/api')

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