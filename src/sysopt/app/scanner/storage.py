import os
import subprocess
import json
from typing import List, Tuple

def find_largest_files(start_path: str = None, max_files: int = 25) -> List[Tuple[int, str]]:
    """
    Scans the given directory (or home directory by default) and returns the largest files.

    This function recursively walks through all subdirectories starting from 'start_path',
    collects file paths and their sizes, and returns the top 'max_files' largest files
    sorted by size in descending order.

    Args:
        start_path (str, optional): The root directory to start scanning from.
                                    If None, defaults to the user's home directory.
        max_files (int, optional): The maximum number of largest files to return.
                                   Defaults to 25.

    Returns:
        List[Tuple[int, str]]: A list of tuples where each tuple contains:
            - int: File size in bytes
            - str: Full path to the file

    Example:
        >>> find_largest_files("/home/user", max_files=5)
        [(1073741824, '/home/user/big_file.dat'), (536870912, '/home/user/another_file.zip'), ...]
    """
    if start_path is None:
        start_path = os.path.expanduser("~")

    files = []

    # Walk through all directories and subdirectories
    for root, _, filenames in os.walk(start_path):
        for filename in filenames:
            full_path = os.path.join(root, filename)

            # Attempt to get file size
            try:
                size = os.path.getsize(full_path)
                files.append((size, full_path))
            except OSError:
                # Skip files that cannot be accessed (e.g., permission denied)
                continue

    sorted_files = sorted(files, key=lambda x: x[0], reverse=True)
    return sorted_files[:max_files]

def format_bytes(size_in_bytes: int) -> str:
    """
    Converts a size in bytes to a human-readable string (e.g., KB, MB, GB).

    Args:
        size_in_bytes (int): Size in bytes.

    Returns:
        str: Human-readable size string (e.g., "2.5 GB", "1024.0 MB").
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_in_bytes < 1024.0:
            return f"{size_in_bytes:.1f} {unit}"
        size_in_bytes /= 1024.0
    return f"{size_in_bytes:.1f} PB"

def print_largest_files(start_path: str = None, max_files: int = 25):
    """
    Prints the largest files found in the given directory in a human-readable format.

    Args:
        start_path (str, optional): Directory to scan. Defaults to home directory.
        max_files (int, optional): Number of largest files to display. Defaults to 25.
    """
    files = find_largest_files(start_path, max_files)
    print(f"Top {len(files)} largest files:")
    for size, path in files:
        print(f"{format_bytes(size):>10} | {path}")

def read_ssd_smart_data() -> dict[str, any]:
    """
    Reads SMART data from all connected drives using 'smartctl' from smartmontools.

    This function runs 'smartctl --json --scan' to list all drives,
    then reads SMART data from each drive using 'smartctl --json --all'.

    Returns:
        Dict[str, Any]: A dictionary mapping device names to their SMART data.
                        Returns empty dict if smartctl is not available.
    """
    try:
        # Scan for drives
        result = subprocess.run(
            ["smartctl", "--json", "--scan"],
            capture_output=True,
            text=True,
            check=True
        )
        scan_data = json.loads(result.stdout)
        drives = scan_data.get("devices", [])

        smart_data = {}
        for drive in drives:
            device_name = drive["name"]
            device_type = drive["type"]

            # Read SMART data for each drive
            smart_result = subprocess.run(
                ["smartctl", "--json", "--all", device_name],
                capture_output=True,
                text=True,
                check=True
            )
            smart_output = json.loads(smart_result.stdout)
            smart_data[device_name] = smart_output

        return smart_data

    except subprocess.CalledProcessError as e:
        print(f"Error running smartctl: {e}")
        return {}
    except FileNotFoundError:
        print("smartctl not found. Please install 'smartmontools'.")
        return {}
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON from smartctl: {e}")
        return {}

def analyze_ssd_health(smart_data: dict[str, any]) -> dict[str, any]:
    """
    Analyzes the health of SSDs based on SMART data.

    Args:
        smart_data (Dict[str, Any]): Output from read_ssd_smart_data().

    Returns:
        Dict[str, Any]: A simplified health report for each drive.
    """
    health_report = {}
    for device, data in smart_data.items():
        drive_health = {"device": device, "status": "Unknown", "attributes": []}

        # Check overall health status
        overall_status = data.get("smart_status", {}).get("passed", None)
        if overall_status is True:
            drive_health["status"] = "Healthy"
        elif overall_status is False:
            drive_health["status"] = "Unhealthy"
        else:
            drive_health["status"] = "Unknown"

        # Extract important SMART attributes (like Reallocated_Sector_Ct, Wear_Leveling_Count, etc.)
        attributes = data.get("ata_smart_attributes", {}).get("table", [])
        for attr in attributes:
            name = attr.get("name", "Unknown")
            value = attr.get("raw", {}).get("value", "N/A")
            threshold = attr.get("thresh", 0)
            flags = attr.get("flags", {}).get("string", "")

            if "Pre-fail" in flags or name in ["Reallocated_Sector_Ct", "Wear_Leveling_Count"]:
                drive_health["attributes"].append({
                    "name": name,
                    "value": value,
                    "threshold": threshold,
                    "flags": flags
                })

        health_report[device] = drive_health

    return health_report

def print_ssd_health_report():
    """
    Reads and prints a simplified SSD health report.
    """
    smart_data = read_ssd_smart_data()
    if not smart_data:
        print("No SMART data available. Make sure 'smartmontools' is installed.")
        return

    health_report = analyze_ssd_health(smart_data)

    for device, report in health_report.items():
        print(f"\nDevice: {device}")
        print(f"Health Status: {report['status']}")
        if report["attributes"]:
            print("Relevant SMART Attributes:")
            for attr in report["attributes"]:
                print(f"  - {attr['name']}: {attr['value']} (Threshold: {attr['threshold']}) [{attr['flags']}]")


if __name__ == "__main__":
    print_largest_files(max_files=10)
    print_ssd_health_report()