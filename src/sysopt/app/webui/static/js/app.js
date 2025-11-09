// App.js - WebUI JavaScript

// Dashboard Updates
async function updateDashboard() {
    try {
        // CPU Load
        const cpuResponse = await fetch('/api/scan/ram?n=1');
        const cpuData = await cpuResponse.json();
        document.getElementById('cpu-load').textContent = cpuData.length > 0 ? 'Active' : 'Low';

        // Memory Usage (simplified)
        document.getElementById('memory-usage').textContent = 'Checking...';

        // Open Ports
        const portsResponse = await fetch('/api/scan/ports?max_port=100');
        const portsData = await portsResponse.json();
        const openPortCount = Object.keys(portsData).length;
        document.getElementById('open-ports').textContent = openPortCount;

        // Autostart Services
        const autorunResponse = await fetch('/api/scan/autorun');
        const autorunData = await autorunResponse.json();
        const totalServices = autorunData.systemd.length + autorunData.user.length;
        document.getElementById('autostart-count').textContent = totalServices;

    } catch (error) {
        console.error('Dashboard update failed:', error);
    }
}

// Scan Functions
async function runScan(scanType, param) {
    const resultsDiv = document.getElementById(`${scanType}-results`);
    resultsDiv.innerHTML = '<p>Scanning...</p>';

    try {
        let url = `/api/scan/${scanType}`;
        if (scanType === 'ram' && param) {
            url += `?n=${param}`;
        } else if (scanType === 'storage') {
            url += '?max_files=10';
        }

        const response = await fetch(url);
        const data = await response.json();

        displayResults(scanType, data, resultsDiv);
    } catch (error) {
        resultsDiv.innerHTML = `<div class="error">Error: ${error.message}</div>`;
    }
}

function runCVECheck(event) {
    event.preventDefault();
    const packageName = document.getElementById('package-name').value;
    const packageVersion = document.getElementById('package-version').value;
    
    const resultsDiv = document.getElementById('cve-results');
    resultsDiv.innerHTML = '<p>Checking CVE...</p>';

    fetch(`/api/scan/cve?name=${encodeURIComponent(packageName)}&version=${encodeURIComponent(packageVersion)}`)
        .then(response => response.json())
        .then(data => displayResults('cve', data, resultsDiv))
        .catch(error => {
            resultsDiv.innerHTML = `<div class="error">Error: ${error.message}</div>`;
        });
}

function displayResults(scanType, data, container) {
    let html = '<ul>';
    
    if (scanType === 'ram') {
        data.forEach(proc => {
            html += `<li><strong>${proc[1]}</strong> (PID: ${proc[2]}) - ${(proc[0]/1024/1024).toFixed(2)} MB</li>`;
        });
    } else if (scanType === 'storage') {
        data.forEach(file => {
            const sizeMB = (file.size / 1024 / 1024).toFixed(2);
            html += `<li><strong>${file.path}</strong> - ${sizeMB} MB</li>`;
        });
    } else if (scanType === 'autorun') {
        html += `<li><strong>Systemd Services (${data.systemd.length}):</strong></li>`;
        data.systemd.slice(0, 10).forEach(service => {
            html += `<li>${service}</li>`;
        });
        html += `<li><strong>User Autostart (${data.user.length}):</strong></li>`;
        data.user.forEach(item => {
            html += `<li>${item}</li>`;
        });
    } else if (scanType === 'ports') {
        const openPorts = Object.keys(data);
        if (openPorts.length > 0) {
            openPorts.forEach(port => {
                html += `<li>Port ${port}: Open</li>`;
            });
        } else {
            html += '<li>No open ports found</li>';
        }
    } else if (scanType === 'cve') {
        if (data.length > 0) {
            data.forEach(vuln => {
                html += `<li><strong>${vuln.id}</strong>: ${vuln.summary || 'No summary'}</li>`;
            });
        } else {
            html += '<li>No vulnerabilities found</li>';
        }
    }
    
    html += '</ul>';
    container.innerHTML = html;
}

// Initialize
document.addEventListener('DOMContentLoaded', function() {
    if (window.location.pathname === '/') {
        updateDashboard();
        // Update every 30 seconds
        setInterval(updateDashboard, 30000);
    }
});