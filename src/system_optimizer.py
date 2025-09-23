#!/usr/bin/env python3
"""
Simple System Optimizer with AI-like recommendations
"""

import psutil
import os
import platform
import subprocess
import time

class SystemOptimizer:
    def __init__(self):
        """
        Initializes the SystemOptimizer with an empty system info dictionary.
        """
        self.system_info = {}
        
    def get_system_info(self):
        """
        Collects basic system information such as CPU usage, memory, disk usage,
        boot time, OS, and architecture.
        
        Returns:
            dict: Dictionary containing system information.
        """
        self.system_info = {
            'cpu_percent': psutil.cpu_percent(interval=1),
            'memory': psutil.virtual_memory(),
            'disk': psutil.disk_usage('/'),
            'boot_time': psutil.boot_time(),
            'os': platform.system(),
            'architecture': platform.machine()
        }
        return self.system_info
    
    def analyze_performance(self):
        """
        Analyzes system performance and generates optimization recommendations
        based on CPU, memory, and disk usage.

        Returns:
            list: List of recommendation dictionaries with type, priority, message, and action.
        """
        recommendations = []
        
        # CPU Analysis
        if self.system_info['cpu_percent'] > 80:
            recommendations.append({
                'type': 'cpu',
                'priority': 'high',
                'message': f'High CPU usage: {self.system_info["cpu_percent"]}% - Check running processes',
                'action': 'Review processes'
            })
        
        # Memory Analysis
        if self.system_info['memory'].percent > 85:
            recommendations.append({
                'type': 'memory',
                'priority': 'high',
                'message': f'High memory usage: {self.system_info["memory"].percent}% - Memory optimization recommended',
                'action': 'Analyze memory usage'
            })
        
        # Disk Usage Check
        if self.system_info['disk'].percent > 90:
            recommendations.append({
                'type': 'storage',
                'priority': 'critical',
                'message': f'Storage almost full: {self.system_info["disk"].percent}% - Free up space',
                'action': 'Free up disk space'
            })
        
        # General recommendation if no issues found
        if len(recommendations) == 0:
            recommendations.append({
                'type': 'general',
                'priority': 'low',
                'message': 'System is stable - no urgent issues detected',
                'action': 'No action required'
            })
        
        return recommendations
    
    def suggest_optimizations(self):
        """
        Displays a formatted system report and performance recommendations.
        """
        print("=== System Report ===")
        print(f"OS: {self.system_info['os']}")
        print(f"Architecture: {self.system_info['architecture']}")
        print(f"CPU Usage: {self.system_info['cpu_percent']}%")
        print(f"RAM Usage: {self.system_info['memory'].percent}%")
        print(f"Storage Usage: {self.system_info['disk'].percent}%")
        print("\n--- Recommendations ---")
        
        recommendations = self.analyze_performance()
        for i, rec in enumerate(recommendations, 1):
            print(f"{i}. [{rec['priority']}] {rec['message']}")
            print(f"   Action: {rec['action']}")
            print()

def main():
    """
    Main function to run the system optimizer.
    Initializes the optimizer, collects system info, and displays recommendations.
    """
    optimizer = SystemOptimizer()
    
    print("Starting System Optimizer...")
    print("Collecting system information...")
    
    # Collect system information
    system_info = optimizer.get_system_info()
    
    # Display optimization suggestions
    optimizer.suggest_optimizations()
    
    
    print("\n--- Features ---")
    print("1. Storage Optimization (e.g. ZRAM)")
    print("2. Find Unnecessary/Unused Programs")
    print("3. Security Scan")
    print("4. GPU Driver Check")

if __name__ == "__main__":
    main()