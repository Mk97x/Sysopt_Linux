from __future__ import annotations

import os
import subprocess
import time
import shutil
from typing import Dict, Any, Optional
from shutil import which
from collections import defaultdict
from pathlib import Path
from .dll_map import DLL_MAP

# ------------------------------------------------------------------
# Detect Bottles Installation
# ------------------------------------------------------------------
def detect_bottles_commands() -> Dict[str, Any]:
    try:
        result = subprocess.run(
            ["flatpak", "list", "--app", "--columns=application"],
            capture_output=True, text=True, check=False
        )
        if "com.usebottles.bottles" in result.stdout:
            return {
                "bottles_cli": ["flatpak", "run", "--command=bottles-cli", "com.usebottles.bottles"],
                "wine_cmd": ["flatpak", "run", "--command=wine", "com.usebottles.bottles"],
                "winetricks": ["flatpak", "run", "--command=winetricks", "com.usebottles.bottles"],
                "winedump": ["flatpak", "run", "--command=winedump", "com.usebottles.bottles"],
                "wineserver": ["flatpak", "run", "--command=wineserver", "com.usebottles.bottles"],
                "type": "flatpak"
            }
    except Exception:
        pass

    if all(which(c) for c in ("bottles-cli", "wine", "winetricks", "wineserver")):
        return {
            "bottles_cli": ["bottles-cli"],
            "wine_cmd": ["wine"],
            "winetricks": ["winetricks"],
            "winedump": ["winedump"],
            "wineserver": ["wineserver"],
            "type": "native"
        }
    raise RuntimeError("No Bottles installation (Flatpak or native) found.")

CMD = detect_bottles_commands()
BOTTLES_CLI = CMD["bottles_cli"]
WINE_CMD = CMD["wine_cmd"]
WINETRICKS = CMD["winetricks"]
WINEDUMP = CMD["winedump"]
WINESERVER = CMD["wineserver"]
INSTALL_TYPE = CMD["type"]

## Todo##
PREFIX_BASE = "/mnt/data"



def map_dll(dll: str) -> Optional[str]:
    return DLL_MAP.get(dll.lower())

def prefix_path(name: str) -> Path:
    return Path(PREFIX_BASE) / name

# ------------------------------------------------------------------
# Global Status Tracker 
# ------------------------------------------------------------------
BOTTLE_STATUS: Dict[str, dict] = defaultdict(lambda: {
    "status": "idle",
    "log": [],
    "candidates": [],
    "subpath": None  # <-- NEU: merkt sich den relevanten Unterordner
})

def log_status(bottle: str, message: str):
    timestamp = time.strftime("%H:%M:%S")
    entry = f"[{timestamp}] {message}"
    BOTTLE_STATUS[bottle]["log"].append(entry)
    BOTTLE_STATUS[bottle]["status"] = "running"
    print(f"[STATUS] {bottle}: {message}")

# ------------------------------------------------------------------
# Bottle Management
# ------------------------------------------------------------------
def create_bottle(name: str, timeout: int = 300) -> bool:
    log_status(name, f"create_bottle: {name}")
    try:
        subprocess.run(
            BOTTLES_CLI + ["new", "--bottle-name", name, "--environment", "gaming"],
            check=True, capture_output=True, text=True, timeout=timeout
        )
        return True
    except subprocess.CalledProcessError as e:
        log_status(name, f"[ERROR] create_bottle (CalledProcessError): {e.stderr[:200]}")
        return False
    except subprocess.TimeoutExpired:
        log_status(name, f"[ERROR] create_bottle: Command timed out after {timeout} seconds")
        return False
    except Exception as e:
        log_status(name, f"[ERROR] create_bottle: {e}")
        return False

def install_dep(bottle: str, dep: str) -> bool:
    log_status(bottle, f"install_dep: {dep} -> {bottle}")
    bottles_comps = {"dxvk", "vkd3d", "dxvk-nvapi"}
    env = os.environ.copy()
    env["WINEPREFIX"] = str(prefix_path(bottle))
    try:
        if dep in bottles_comps:
            cmd = BOTTLES_CLI + ["add", "-b", bottle, "-n", dep, "-p", "dummy"]
        else:
            cmd = WINETRICKS + [dep]
        result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=600)
        if result.returncode == 0 or "already installed" in result.stdout:
            log_status(bottle, f"  ✓ {dep}")
            return True
        log_status(bottle, f"  ✗ {dep} – {result.stderr[:200]}")
        return False
    except Exception as e:
        log_status(bottle, f"[ERROR] install_dep: {e}")
        return False

def wait_until_wineserver_idle(bottle: str):
    env = os.environ.copy()
    env["WINEPREFIX"] = str(prefix_path(bottle))
    for _ in range(300):
        try:
            subprocess.run(WINESERVER + ["--wait"], env=env, check=True, timeout=10)
            return
        except subprocess.TimeoutExpired:
            time.sleep(2)
    log_status(bottle, "[WARN] wineserver --wait timeout")

def copy_folder_to_bottle(bottle: str, src: str, target_subdir: str) -> bool:
    prefix = prefix_path(bottle) / "drive_c" / target_subdir
    prefix.parent.mkdir(parents=True, exist_ok=True)
    try:
        if prefix.exists():
            shutil.rmtree(prefix)
        shutil.copytree(src, prefix, symlinks=True)
        log_status(bottle, f"[MCP] copied {src} -> {prefix}")
        return True
    except Exception as e:
        log_status(bottle, f"[ERROR] copy_folder: {e}")
        return False

# ------------------------------------------------------------------
# Shortcut Creation (with correct context)
# ------------------------------------------------------------------
def create_shortcut_in_bottle(bottle: str, exe_path: Path):
    prefix = prefix_path(bottle)
    if not exe_path.is_relative_to(prefix):
        log_status(bottle, f"[ERROR] EXE not inside bottle: {exe_path}")
        return False

    rel_path = exe_path.relative_to(prefix)
    shortcut_path = str(rel_path)
    if shortcut_path.startswith("drive_c/"):
        shortcut_path = shortcut_path[8:]

    env = os.environ.copy()
    env["WINEPREFIX"] = str(prefix)
    working_dir = prefix / "drive_c"

    log_status(bottle, f"[DEBUG] Creating shortcut in cwd={working_dir} with path='{shortcut_path}'")

    try:
        cmd = BOTTLES_CLI + ["add", "-b", bottle, "-n", exe_path.stem, "-p", shortcut_path]
        result = subprocess.run(
            cmd,
            env=env,
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            log_status(bottle, f"[MCP] Shortcut created: {exe_path.stem}")
            return True
        else:
            log_status(bottle, f"[ERROR] Shortcut failed: {result.stderr.strip()}")
            return False
    except Exception as e:
        log_status(bottle, f"[ERROR] Exception in shortcut creation: {e}")
        return False