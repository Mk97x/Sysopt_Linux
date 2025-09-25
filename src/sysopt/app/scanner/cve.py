import platform
import subprocess
import json
from typing import List, Dict

OSV_API = "https://api.osv.dev/v1/query"

def check_package_cves(name: str, version: str) -> List[Dict]:
    payload = {"package": {"name": name}, "version": version}
    try:
        r = requests.post(OSV_API, json=payload, timeout=10)
        if r.status_code == 200:
            return r.json().get("vulns", [])
    except Exception:
        pass
    return []

def scan_system_packages():
    packages = get_installed_packages()
    print(f"Scanning {len(packages)} packages...")
    all_vulns = []
    for pkg in packages:
        name, version = pkg["name"], pkg["version"]
        print(f"Checking {name}=={version} ...")
        vulns = check_package_cves(name, version)
        if vulns:
            print(f"  ❗ Found {len(vulns)} vulnerability(ies)")
            all_vulns.append({"package": pkg, "vulns": vulns})
        else:
            print(f"No known vulnerabilities")
    return all_vulns

def get_installed_packages() -> List[Dict[str, str]]:
    """
    Fetches a list of installed packages on the system based on the operating system.

    This function detects the current OS and calls the appropriate helper function
    to retrieve installed packages using system-specific tools like:
    - `dpkg` on Debian/Ubuntu systems
    - `pacman` on Arch Linux systems
    - `rpm` on Fedora/RHEL/CentOS systems
    - `brew` on macOS

    Returns:
        List[Dict[str, str]]: A list of dictionaries where each dictionary contains:
            - "name": The name of the package (e.g., "python3", "curl")
            - "version": The installed version of the package (e.g., "3.9.2-1")

    Example:
        [
            {"name": "curl", "version": "7.74.0-1.3+b1"},
            {"name": "python3", "version": "3.9.2-3"}
        ]
    """
    system = platform.system()

    # Detect the operating system and call the corresponding helper function
    if system == "Linux":
        try:
            # Attempt to detect the Linux distribution using freedesktop.org standard
            distro = platform.freedesktop_os_release().get("ID", "")
        except Exception:
            # Fallback if the OS release file is not available or readable
            distro = ""
            print("Warning: Could not determine Linux distribution, defaulting to dpkg method.")

        # Choose the correct package manager based on the detected distribution
        if distro in ["ubuntu", "debian", "raspbian"]:
            return _get_deb_packages()
        elif distro in ["arch", "manjaro", "artix"]:
            return _get_arch_packages()
        elif distro in ["fedora", "rhel", "centos", "almalinux", "rocky"]:
            return _get_rpm_packages()
        else:
            # Default to dpkg if distribution is unknown or not explicitly handled
            print(f"Warning: Unknown Linux distribution '{distro}', attempting dpkg method...")
            return _get_deb_packages()

    elif system == "Darwin":  # macOS
        # macOS typically uses Homebrew as a package manager
        return _get_brew_packages()

    else:
        # For unsupported operating systems, return an empty list
        print(f"Warning: Unsupported operating system: {system}")
        return []

def _get_deb_packages() -> List[Dict[str, str]]:
    """
    Helper function to retrieve installed packages on Debian-based systems (e.g., Ubuntu).

    Uses the `dpkg -l` command to list all installed packages.
    The output format is parsed to extract package name and version.

    Returns:
        List[Dict[str, str]]: List of packages in the form {"name": ..., "version": ...}
    """
    try:
        # Run 'dpkg -l' to list installed packages
        result = subprocess.run(
            ["dpkg", "-l"], 
            capture_output=True, 
            text=True, 
            check=True  # Raise exception if command fails
        )
        
        # Split the output into lines, skipping the header (first 5 lines)
        lines = result.stdout.splitlines()[5:]
        
        packages = []
        for line in lines:
            # Lines starting with "ii" indicate installed packages
            if line.startswith("ii "):
                # Split the line into parts: status, name, version, description
                parts = line.split()
                if len(parts) >= 3:
                    name = parts[1]      # Package name
                    version = parts[2]   # Package version
                    packages.append({"name": name, "version": version})
        return packages
    except Exception as e:
        print(f"Error reading dpkg packages: {e}")
        return []

def _get_arch_packages() -> List[Dict[str, str]]:
    """
    Helper function to retrieve installed packages on Arch Linux-based systems.

    Uses the `pacman -Q` command to list all installed packages.
    The output is in the format: <package_name> <version>

    Returns:
        List[Dict[str, str]]: List of packages in the form {"name": ..., "version": ...}
    """
    try:
        # Run 'pacman -Q' to list installed packages
        result = subprocess.run(
            ["pacman", "-Q"], 
            capture_output=True, 
            text=True, 
            check=True
        )
        
        lines = result.stdout.strip().splitlines()
        
        packages = []
        for line in lines:
            # Each line is in format: package_name version
            parts = line.split()
            if len(parts) >= 2:
                name = parts[0]
                version = parts[1]
                packages.append({"name": name, "version": version})
        return packages
    except Exception as e:
        print(f"Error reading pacman packages: {e}")
        return []

def _get_rpm_packages() -> List[Dict[str, str]]:
    """
    Helper function to retrieve installed packages on RPM-based systems (e.g., Fedora, RHEL, CentOS).

    Uses the `rpm -qa` command with a custom query format to extract name and version.
    The format string ensures consistent output.

    Returns:
        List[Dict[str, str]]: List of packages in the form {"name": ..., "version": ...}
    """
    try:
        # Run 'rpm -qa' with a custom format to get name and version only
        result = subprocess.run(
            ["rpm", "-qa", "--queryformat", "%{NAME} %{VERSION}-%{RELEASE}\n"],
            capture_output=True,
            text=True,
            check=True
        )
        
        lines = result.stdout.strip().splitlines()
        
        packages = []
        for line in lines:
            # Each line is in format: package_name version-release
            parts = line.split(maxsplit=1)  # Split only at first space to avoid splitting version
            if len(parts) == 2:
                name, version = parts
                packages.append({"name": name, "version": version})
        return packages
    except Exception as e:
        print(f"Error reading rpm packages: {e}")
        return []

def _get_brew_packages() -> List[Dict[str, str]]:
    """
    Helper function to retrieve installed packages on macOS using Homebrew.

    Uses the `brew list --versions` command to list installed packages with their versions.

    Returns:
        List[Dict[str, str]]: List of packages in the form {"name": ..., "version": ...}
    """
    try:
        # Run 'brew list --versions' to get installed packages with versions
        result = subprocess.run(
            ["brew", "list", "--versions"],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Split output into lines
        lines = result.stdout.strip().splitlines()
        
        packages = []
        for line in lines:
            # Each line is in format: package_name version1 version2 ...
            parts = line.split()
            if len(parts) >= 2:
                name = parts[0]      # Package name
                version = parts[1]   # First version (usually the active one)
                packages.append({"name": name, "version": version})
        return packages
    except Exception as e:
        print(f"Error reading Homebrew packages: {e}")
        return []



if __name__ == "__main__":
    vulns = scan_system_packages()
    print("\n--- Summary ---")
    for item in vulns:
        pkg = item['package']
        print(f"\nPackage: {pkg['name']}=={pkg['version']}")
        for v in item['vulns']:
            print(f"  - {v.get('id')} - {v.get('summary', 'No summary')}")
