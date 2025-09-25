import psutil
from typing import List, Tuple


def top_memory_processes(n=10):
    """
    Returns a list of the top 'n' processes consuming the most physical memory (RSS).

    This function iterates through all currently running processes and collects
    their memory usage (Resident Set Size - RSS), which represents the portion
    of memory that is held in RAM. It then sorts the processes by memory usage
    in descending order and returns the top 'n' entries.

    Args:
        n (int): The number of top memory-consuming processes to return.
                 Defaults to 10. If set to a higher number than available
                 processes, all processes will be returned.

    Returns:
        List[Tuple]: A list of tuples, each containing:
            - int: Memory usage in bytes (RSS - Resident Set Size)
            - str: Name of the process
            - int: Process ID (PID)

    Example:
        >>> top_memory_processes(3)
        [(123456789, 'firefox', 1234), (987654321, 'chrome', 5678), (456123789, 'code', 91011)]
    """
    procs = []
    for proc in psutil.process_iter(['pid', 'name', 'memory_info']):
        try:
            mem = proc.info['memory_info'].rss
            procs.append((mem, proc.info['name'], proc.info['pid']))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return sorted(procs, key=lambda x: x[0], reverse=True)[:n]

def top_processes(n: int = 10, sort_by: str = "memory") -> List[Tuple]:
    """
    Returns a list of top processes based on memory or CPU usage.

    Args:
        n (int): Number of top processes to return (default: 10)
        sort_by (str): Sort by "memory" or "cpu" (default: "memory")

    Returns:
        List[Tuple]: Each tuple contains (value, name, pid)
                     - For memory: (RSS in bytes, name, pid)
                     - For CPU: (CPU %, name, pid)
    """
    procs = []
    for proc in psutil.process_iter(['pid', 'name', 'memory_info', 'cpu_percent']):
        try:
            # Ensure the CPU percent is updated by calling it once
            cpu_percent = proc.cpu_percent()
            mem_info = proc.memory_info()
            name = proc.info['name']
            pid = proc.info['pid']

            if sort_by == "memory":
                value = mem_info.rss  # RSS = Resident Set Size (physical memory used)
                procs.append((value, name, pid))
            elif sort_by == "cpu":
                procs.append((cpu_percent, name, pid))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            # Process may have terminated or is not accessible
            pass

    sorted_procs = sorted(procs, key=lambda x: x[0], reverse=True)
    return sorted_procs[:n]

def top_memory_processes(n: int = 10) -> List[Tuple]:
    """
    Returns top processes by memory usage (RSS).
    """
    return top_processes(n, sort_by="memory")

def top_cpu_processes(n: int = 10) -> List[Tuple]:
    """
    Returns top processes by CPU usage percentage.
    """
    return top_processes(n, sort_by="cpu")

if __name__ == "__main__":
    print("Top 10 memory-consuming processes:")
    for mem, name, pid in top_memory_processes(10):
        print(f"PID: {pid:<8} | Memory: {mem / 1024 / 1024:.2f} MB | Name: {name}")

    print("\nTop 10 CPU-consuming processes:")
    for cpu, name, pid in top_cpu_processes(10):
        print(f"PID: {pid:<8} | CPU: {cpu:>5.2f}% | Name: {name}")


