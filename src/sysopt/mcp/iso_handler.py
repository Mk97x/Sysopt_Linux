
from __future__ import annotations

import os
import subprocess
import shutil
from pathlib import Path
from typing import Optional
from shutil import which


from contextlib import contextmanager

from .bottles_handler import log_status, BOTTLES_CLI

# ------------------------------------------------------------------
# ISO handling (7z only)
# ------------------------------------------------------------------
@contextmanager
def mount_iso(iso_path: str, target_dir: Optional[Path] = None):
    iso_path = Path(iso_path).resolve()
    if not iso_path.is_file():
        raise FileNotFoundError(f"ISO not found: {iso_path}")

    use_temp = target_dir is None
    if use_temp:
        target_dir = Path("/mnt/data/TEMP") / iso_path.stem
        shutil.rmtree(target_dir, ignore_errors=True)
        target_dir.mkdir(parents=True, exist_ok=True)

    if not which("7z"):
        shutil.rmtree(target_dir, ignore_errors=True)
        raise RuntimeError("7z is required but not found.")

    try:
        log_status("system", f"[MCP] Extracting ISO with 7z: {iso_path} -> {target_dir}")
        subprocess.run(["7z", "x", str(iso_path), f"-o{target_dir}"], check=True, capture_output=True)
    except Exception as e:
        if use_temp:
            log_status("system", f"[MCP] 7z failed: {e}")
        else:
            shutil.rmtree(target_dir, ignore_errors=True)
            raise RuntimeError(f"7z extraction failed: {e}")

    if use_temp and not any(target_dir.iterdir()):
        shutil.rmtree(target_dir, ignore_errors=True)
        raise RuntimeError(f"Empty extraction: {target_dir}")

    log_status("system", f"[MCP] ISO extracted with 7z")
    try:
        yield target_dir
    finally:
        if use_temp:
            shutil.rmtree(target_dir, ignore_errors=True)

def run_setup_in_bottle(bottle_name: str, setup_path: Path):
    cmd = BOTTLES_CLI + ["run", "--bottle", bottle_name, str(setup_path)]
    log_status(bottle_name, f"[MCP] Running installer via: {' '.join(cmd)}")
    subprocess.run(cmd, check=False)

def find_setup_exe_in_iso(mount_point: Path) -> Optional[Path]:
    candidates = ["setup.exe", "install.exe", "autorun.exe", "start.exe"]
    for root, dirs, files in os.walk(mount_point):
        depth = len(Path(root).relative_to(mount_point).parts)
        if depth > 1:
            continue
        for f in files:
            if f.lower() in candidates:
                return Path(root) / f
    return None