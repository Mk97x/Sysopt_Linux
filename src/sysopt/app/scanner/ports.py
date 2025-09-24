import socket          # connect to network ports
from concurrent.futures import ThreadPoolExecutor  # run multiple tasks at the same time
from typing import Dict 

def scan_port(host, port, timeout=0.5):
    """
    This function checks if a single port on a computer is open or closed.
    
    Args:
        host (str): The computer we want to check (e.g. "127.0.0.1" or "google.com")
        port (int): The port number we want to check (e.g. 80 for web, 22 for SSH)
        timeout (float): How long to wait before giving up (in seconds)
    
    Returns:
        bool: True if the port is open, False if it's closed
    """
    
    # AF_INET = IPv4 addresses
    # SOCK_STREAM = using TCP (not UDP)
    socket_obj = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    socket_obj.settimeout(timeout)
    
    try:       
        socket_obj.connect((host, port))
        # port is open if we reach here
        socket_obj.close()  # Close the connection
        return True
        
    except Exception as e:
        socket_obj.close()  # Close the connection
        print(f"Error: {e}")
        return False


def scan_ports(host, ports=None, workers=50):
    """
    This function checks multiple ports on a computer at the same time.
    It uses multiple threads to make the scanning faster.
    
    Args:
        host (str): The computer we want to check
        ports (list): List of port numbers to check (if None, checks all ports 1-65535)
        workers (int): How many connections to try at the same time
    
    Returns:
        dict: A dictionary with open ports as keys and True as values
              Example: {22: True, 80: True, 443: True}
    """
    
    # If no ports are given, check all possible ports (1 to 65535)
    if ports is None:
        ports = list(range(1, 65536))  
    
    results = {}
    
    executor = ThreadPoolExecutor(max_workers=workers)
    future_to_port = {}
    
    # Submit all the port scanning tasks to the executor
    for port in ports:
        future = executor.submit(scan_port, host, port)
        future_to_port[future] = port
    
    for future in future_to_port:
        port = future_to_port[future]  
        is_open = future.result()     
        
        results[port] = is_open
    
    # Close the executor 
    executor.shutdown()
    
    open_ports = {}
    for port, is_open in results.items():
        if is_open:  
            open_ports[port] = is_open
    
    return open_ports

if __name__ == "__main__":
    # Check ports 22 (SSH), 80 (HTTP), 443 (HTTPS), 9000 (custom)
    result = scan_ports("127.0.0.1", ports=[22, 80, 443, 9000])
    print("Open ports:", result)
    
    # Explanation of common ports:
    print("\nCommon port numbers:")
    print("- Port 22: SSH (secure shell)")
    print("- Port 80: HTTP (web server)")
    print("- Port 443: HTTPS (secure web server)")
    print("- Port 9000: Often used for custom applications")