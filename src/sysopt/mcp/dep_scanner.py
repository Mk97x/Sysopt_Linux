import os
import subprocess
import re
from typing import Dict, Any, List
from pathlib import Path


from .dll_map import DLL_MAP

def map_dll(dll: str) -> str | None:
    return DLL_MAP.get(dll.lower())

# ------------------------------------------------------------------
# Dependency Scan (Wine Debug)
# ------------------------------------------------------------------
def scan_deps_wine(
    program: str,
    wineprefix: str,
    wine_cmd: List[str],
    timeout: int = 10
) -> Dict[str, Any]:
    if not os.path.isfile(program):
        return {"success": False, "error": "file not found"}
    env = os.environ.copy()
    env["WINEPREFIX"] = wineprefix
    env["WINEDEBUG"] = "+loaddll"
    env["LIBGL_ALWAYS_SOFTWARE"] = "1"
    env["GALLIUM_DRIVER"] = "llvmpipe"
    try:
        proc = subprocess.Popen(
            wine_cmd + [program],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        try:
            _, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            _, stderr = proc.communicate()
        loaded, missing = set(), set()
        patterns = [
            r"load(?:ed)?\s+library\s+['\"]?([^\s]+\.dll)['\"]?",
            r"Loaded module\s+['\"]?([^\s]+\.dll)['\"]?",
            r"err:module:.*?\s+['\"]?([^\s]+\.dll)['\"]?",
            r"Could not load\s+['\"]?([^\s]+\.dll)['\"]?",
            r"failed to (?:open|load).*?['\"]?([^\s]+\.dll)['\"]?",
        ]
        for pat in patterns:
            for dll in re.findall(pat, stderr, re.I):
                if "err" in pat or "fail" in pat:
                    missing.add(dll)
                else:
                    loaded.add(dll)
        deps = {map_dll(d) for d in loaded | missing} - {None}
        return {
            "success": True,
            "dependencies": sorted(deps),
            "missing_dlls": sorted(missing)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

# ------------------------------------------------------------------
# Static PE Scan
# ------------------------------------------------------------------
def scan_deps_static(program: str, winedump_cmd: List[str]) -> Dict[str, Any]:
    try:
        result = subprocess.run(
            winedump_cmd + ["-j", program],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr)
        dlls = re.findall(r"(?i)DLL Name:\s+([^\s]+\.dll)", result.stdout)
        deps = {map_dll(d) for d in dlls} - {None}
        return {
            "success": True,
            "dependencies": sorted(deps),
            "dlls": dlls
        }
    except Exception as e:
        return {"success": False, "error": str(e)}