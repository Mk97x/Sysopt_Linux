#!/usr/bin/env python3
"""
Bottles-MCP-Server v2

A Model Context Protocol (MCP) server for automating Wine bottle setup via Bottles CLI.
Works exclusively with Flatpak-based Bottles installation (com.usebottles.bottles).

Features:
  - Create new gaming bottles with automated dependency detection
  - Scan Windows executables for required DLL dependencies using WINEDEBUG
  - Install dependencies via winetricks (standard verbs) or bottles-cli (GPU components)
  - Analyze dependencies without installation
  - Install dependencies into existing bottles

Current limitations:
  - Cannot detect dependencies if the target executable fails to run
  - Interactive platform installers (Steam, Ubisoft Connect) must be set up manually first
  - GPU acceleration may be limited inside Flatpak sandbox
  - Only valid winetricks verbs and bottles-cli components are supported (ubisoft launcher and dx11 seems to make trouble)
"""

from __future__ import annotations

import os
import subprocess
import json
import re
import threading
from pathlib import Path
from typing import Optional, Set, List, Dict


from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

# ==============================================================================
# CONFIGURATION
# ==============================================================================

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Flatpak command wrappers - these ensure commands run inside the Bottles Flatpak container
BOTTLES_CLI = ["flatpak", "run", "--command=bottles-cli", "com.usebottles.bottles"]
WINE_CMD = ["flatpak", "run", "--command=wine", "com.usebottles.bottles"]
WINETRICKS = ["flatpak", "run", "--command=winetricks", "com.usebottles.bottles"]

# Base directory where Bottles stores wine prefixes
PREFIX_BASE = "/mnt/data"

# ==============================================================================
# DLL TO COMPONENT MAPPING
# ==============================================================================

DLL_MAP: Dict[str, str] = {
    """
    Maps Windows DLL filenames to installable winetricks verbs or bottles-cli components.
    
    IMPORTANT NOTES:
    - Only includes verbs that actually exist in winetricks (verified Jan 2025)
    - GPU components (dxvk, vkd3d) are installed via bottles-cli, not winetricks
    - d3d11.dll maps to dxvk (not d3dx11, which doesn't exist as a verb)
    - Platform loaders (Steam, Ubisoft) map to their respective platform components
    - If a DLL has no mapping, it will be ignored during scanning
    """
    
    # DirectX/Graphics - DXVK handles d3d11/d3d12 translation to Vulkan
    "d3d9.dll": "d3dx9",
    "d3d10.dll": "d3dx10",
    "d3d11.dll": "dxvk",
    "d3d11_1.dll": "dxvk",
    "d3d11_2.dll": "dxvk",
    "d3d11_3.dll": "dxvk",
    "d3d11_4.dll": "dxvk",
    "d3d12.dll": "vkd3d",
    "d3dcompiler_43.dll": "d3dcompiler_43",
    "d3dcompiler_47.dll": "d3dcompiler_47",
    "dxgi.dll": "dxvk",
    
    # Input & Audio
    "xinput1_3.dll": "xinput",
    "xinput1_4.dll": "xinput",
    "dinput8.dll": "dinput",
    "openal32.dll": "openal",
    "fmod.dll": "fmod",
    "fmodex.dll": "fmod",
    
    # Video Codecs
    "binkw32.dll": "bink",
    "binkw64.dll": "bink",
    "bink2w32.dll": "bink2",
    "bink2w64.dll": "bink2",
    
    # Physics & Acceleration
    "physxloader.dll": "physx",
    "physx3_x86.dll": "physx",
    "physx3_x64.dll": "physx",
    
    # GPU/VR
    "openvr_api.dll": "openvr",
    "nvapi.dll": "dxvk-nvapi",
    
    # Platform/Store Loaders
    "ubiorbitapi_r2.dll": "ubisoftconnect",
    "uplay_r1.dll": "ubisoftconnect",
    "uplay_r1_loader.dll": "ubisoftconnect",
    
    # .NET Runtime
    "mscoree.dll": "dotnet40",
    "clr.dll": "dotnet40",
    "system.dll": "dotnet40",
    
    # Visual C++ Runtimes
    "msvcp140.dll": "vcrun2019",
    "vcruntime140.dll": "vcrun2019",
    "msvcp140_1.dll": "vcrun2019",
    "msvcp140_2.dll": "vcrun2019",
    "vcomp140.dll": "vcrun2019",
    "vcruntime140_1.dll": "vcrun2019",
    "vcruntime150.dll": "vcrun2022",
    "msvcp150.dll": "vcrun2022",
    "vcomp150.dll": "vcrun2022",
    "msvcp60.dll": "vcrun6",
    "msvcrt.dll": "vcrun6",
    "msvcp71.dll": "vcrun2003",
    "msvcp80.dll": "vcrun2005",
    "msvcp90.dll": "vcrun2008",
    "msvcp100.dll": "vcrun2010",
    "msvcp110.dll": "vcrun2012",
    "msvcp120.dll": "vcrun2013",
    
    # System Libraries
    "mfc42.dll": "mfc42",
    "msxml3.dll": "msxml3",
    "msxml6.dll": "msxml6",
    "quartz.dll": "quartz",
    "riched20.dll": "riched20",
    "tahoma.ttf": "tahoma",
    "arial.ttf": "corefonts",
    "winhttp.dll": "winhttp",
    "wininet.dll": "wininet",
    "wsock32.dll": "wsock32",
    "iphlpapi.dll": "iphlpapi",
}

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def map_dll(dll: str) -> Optional[str]:
    """
    Look up a DLL filename in the mapping table.
    
    Args:
        dll: Windows DLL filename (e.g., "d3d11.dll")
        
    Returns:
        Component name if mapped, None otherwise
    """
    return DLL_MAP.get(dll.lower())


def register_bottle_in_gui(bottle_name: str, bottle_path: str) -> None:
    registry_dir = Path.home() / ".var/app/com.usebottles.bottles/data/bottles/bottles"
    registry_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "name": bottle_name,
        "path": bottle_path,
        "environment": "gaming",
        "runner": "soda-7.0-9",
        "dxvk": True,
        "vkd3d": False,
        "dxvk_nvapi": False,
        "arch": "win64"
    }
    (registry_dir / f"{bottle_name}.json").write_text(json.dumps(payload, indent=2))

def extract_dlls_static(exe_path: str) -> List[str]:
    if not os.path.isfile(exe_path):
        raise FileNotFoundError(exe_path)
    try:
        result = subprocess.run(
            ["flatpak", "run", "--command=winedump", "com.usebottles.bottles",
             "-j", exe_path],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip())
        # DLL Name: xxxx.dll
        return re.findall(r"(?i)DLL Name:\s+([^\s]+\.dll)", result.stdout)
    except Exception as e:
        raise RuntimeError(f"winedump failed: {e}")



def analyze_dependencies_static(program_path: str) -> Dict:
    try:
        dlls = extract_dlls_static(program_path)
        deps = {map_dll(d) for d in dlls}
        deps.discard(None)
        return {
            "success": True,
            "dependencies": sorted(deps),
            "dlls": dlls
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def prefix_path_for(bottle_name: str) -> str:
    """
    Compute the wine prefix path for a given bottle name.
    
    Args:
        bottle_name: Name of the Bottles bottle
        
    Returns:
        Full path to the WINEPREFIX directory
    """
    return os.path.join(PREFIX_BASE, bottle_name)


def create_bottle(bottle_name: str) -> bool:
    """
    Create a new gaming bottle using bottles-cli.
    
    Args:
        bottle_name: Name for the new bottle
        
    Returns:
        True if bottle creation succeeded, False otherwise
    """
    print(f"[MCP] Creating bottle: {bottle_name}")
    try:
        cmd = BOTTLES_CLI + ["new", "--bottle-name", bottle_name, "--environment", "gaming"]
        register_bottle_in_gui(bottle_name, prefix_path_for(bottle_name))
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        print(f"[DEBUG] create_bottle stdout: {result.stdout[:200]}")
        print(f"[DEBUG] create_bottle stderr: {result.stderr[:200]}")
        return result.returncode == 0
    except Exception as e:
        print(f"[ERROR] create_bottle failed: {e}")
        return False


def install_bottle_dependency(bottle_name: str, dependency: str) -> bool:
    """
    Install a single dependency into a bottle.
    
    Uses bottles-cli for GPU-accelerated components (dxvk, vkd3d, etc.)
    and winetricks for standard verb packages (vcrun*, d3dx*, etc.).
    
    Args:
        bottle_name: Name of the target bottle
        dependency: Component to install (e.g., "dxvk", "vcrun2019")
        
    Returns:
        True if installation succeeded or component was already installed,
        False if installation failed
    """
    print(f"[MCP] Installing '{dependency}' into '{bottle_name}'")
    
    # Components that must be installed via bottles-cli (GPU-related)
    bottles_cli_components = {"dxvk", "vkd3d", "dxvk-nvapi"}
    
    try:
        env = os.environ.copy()
        env["WINEPREFIX"] = prefix_path_for(bottle_name)
        
        if dependency in bottles_cli_components:
            print(f"[MCP]   → Using bottles-cli")
            cmd = BOTTLES_CLI + [
                                "add",
                                "-b", bottle_name,
                                "-n", dependency,
                                "-p", "dummy"          
                            ]
            result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=600)
        else:
            print(f"[MCP]   → Using winetricks")
            cmd = WINETRICKS + [dependency]
            result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=600)
            
            # If component was already installed, that still counts as success
            if "already installed" in result.stdout:
                print(f"[MCP]   ✓ {dependency} already installed")
                return True
        
        success = result.returncode == 0
        if success:
            print(f"[MCP]   ✓ {dependency} installed successfully")
        else:
            print(f"[MCP]   ✗ {dependency} failed (rc={result.returncode})")
            if result.stderr:
                print(f"[DEBUG]   stderr: {result.stderr[:300]}")
        
        return success
        
    except subprocess.TimeoutExpired:
        print(f"[ERROR] {dependency} timeout (installation took too long)")
        return False
    except Exception as e:
        print(f"[ERROR] {dependency} exception: {e}")
        return False


def run_wine_dependency_solver(program_path: str, bottle_name: str, timeout: int = 10) -> Dict:
    """
    Execute a Windows program with WINEDEBUG enabled to capture DLL load attempts.
    
    This is the core scanning mechanism: Wine logs all DLL load attempts to stderr,
    including which DLLs were successfully loaded and which failed to load.
    We parse these logs to determine what components the program needs.
    
    IMPORTANT: This can only work if the program starts successfully. If the program
    fails to initialize (missing critical DLLs, incompatible Wine version, etc.),
    no DLLs will be logged and the scan will return empty results.
    
    Args:
        program_path: Full path to the Windows executable
        bottle_name: Name of the bottle to scan in
        timeout: Maximum seconds to let the program run (default 10)
        
    Returns:
        Dictionary with keys:
          - success (bool): Whether scanning succeeded
          - dependencies (list): Detected component requirements
          - missing_dlls (list): Raw DLL names that failed to load
          - error (str): Error message if success is False
    """
    print(f"[MCP] WINEDEBUG scanning: {program_path}")
    if not os.path.isfile(program_path):
        return {"success": False, "error": f"File not found: {program_path}"}

    env = os.environ.copy()
    env["WINEDEBUG"] = "+loaddll"
    env["WINEPREFIX"] = prefix_path_for(bottle_name)
    # Software rendering fallbacks for GPU-restricted environments
    env["LIBGL_ALWAYS_SOFTWARE"] = "1"
    env["GALLIUM_DRIVER"] = "llvmpipe"
    env["MESA_GL_VERSION_OVERRIDE"] = "3.3"

    try:
        proc = subprocess.Popen(
            WINE_CMD + [program_path],
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

        # Parse Wine debug output for DLL loading info
        # Format: "load dll ... : <dllname>"
        # Match any line mentioning a dll load or failure
        dll_patterns = [
        r"load(?:ed)?\s+library\s+['\"]?([A-Za-z0-9_\-\.]+\.dll)['\"]?",  # loaded library 'X.dll'
        r"Loaded module\s+['\"]?([A-Za-z0-9_\-\.]+\.dll)['\"]?",        # Loaded module X.dll
        r"err:module:.*?\s+['\"]?([A-Za-z0-9_\-\.]+\.dll)['\"]?",      # err:module... X.dll
        r"Could not load\s+['\"]?([A-Za-z0-9_\-\.]+\.dll)['\"]?",      # Could not load X.dll
        r"failed to (?:open|load).*?['\"]?([A-Za-z0-9_\-\.]+\.dll)['\"]?",
        r"cannot open.*?['\"]?([A-Za-z0-9_\-\.]+\.dll)['\"]?",
]

        loaded = set()
        missing = set()

        for pat in dll_patterns:
            found = re.findall(pat, stderr, re.I)
            for dll in found:
                if "err:" in pat or "failed" in pat or "cannot" in pat or "Could not" in pat:
                    missing.add(dll)
                else:
                    loaded.add(dll)


        # Map raw DLL names to installable components
        deps: Set[str] = set()
        for d in loaded | missing:
            mapped = map_dll(d)
            if mapped:
                deps.add(mapped)

        print(f"[MCP] Scan found {len(deps)} dependencies: {sorted(deps)}")
        return {
            "success": True,
            "dependencies": sorted(deps),
            "missing_dlls": sorted(missing)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def sanitize_bottle_env(bottle_name: str) -> None:
    """
    Perform minimal sanitization on a newly created bottle.
    
    Current implementation:
      - wineboot --repair: Fixes any initialization issues in the Wine prefix
      
    This is kept minimal to avoid corrupting the bottle. Heavy-handed modifications
    (like forcing specific runners or installing unnecessary components) are avoided.
    
    Args:
        bottle_name: Name of the bottle to sanitize
    """
    print(f"[MCP] Sanitizing bottle: {bottle_name}")
    env = os.environ.copy()
    env["WINEPREFIX"] = prefix_path_for(bottle_name)

    try:
        subprocess.run(
            ["flatpak", "run", "--command=wine", "com.usebottles.bottles", "wineboot", "--repair"],
            env=env,
            capture_output=True,
            timeout=60,
            check=False
        )
        print(f"[MCP] Sanitization complete")
    except Exception as e:
        print(f"[WARN] Sanitization failed: {e}")


# ==============================================================================
# MCP PROTOCOL ENDPOINTS
# ==============================================================================

@app.post("/")
async def handle_mcp_request(request: Request):
    body = await request.json()
    method, req_id = body.get("method"), body.get("id")
    print(f"[DEBUG] MCP Request: method={method}, id={req_id}")

    # ---- initialize ------------------------------------------------
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": req_id,
                "result": {"protocolVersion": "2024-11-05",
                           "serverInfo": {"name": "BottleAutomator", "version": "2.1.0"},
                           "capabilities": {"tools": {}, "resources": {}, "prompts": {}}}}

    # ---- tools/list ------------------------------------------------
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id,
                "result": {"tools": [
                    {"name": "bottles_installer",
                     "description": "Create bottle, scan deps, install (bg)",
                     "inputSchema": {"type": "object",
                                     "properties": {"program_path": {"type": "string"},
                                                    "bottle_name": {"type": "string"}},
                                     "required": ["program_path", "bottle_name"]}},
                    {"name": "analyze_dependencies",
                     "description": "Scan PE file for DLL deps (dry-run)",
                     "inputSchema": {"type": "object",
                                     "properties": {"program_path": {"type": "string"}},
                                     "required": ["program_path"]}},
                    {"name": "bottles_install_deps",
                     "description": "Scan & install deps into existing bottle (bg)",
                     "inputSchema": {"type": "object",
                                     "properties": {"program_path": {"type": "string"},
                                                    "bottle_name": {"type": "string"}},
                                     "required": ["program_path", "bottle_name"]}}
                ]}}

    # ---- tools/call ------------------------------------------------
    if method in ("call", "tools/call"):
        params = body.get("params", {})
        tool_name = params.get("name") or params.get("toolName")
        args = params.get("arguments") or params

        # ---------- bottles_installer ------------------------------
        if tool_name == "bottles_installer":
            program_path = args.get("program_path") or args.get("exe_path")
            bottle_name = args.get("bottle_name")

            # normalizing List -> str
            if isinstance(program_path, list):
                program_path = program_path[0] if program_path else ""
            if isinstance(bottle_name, list):
                bottle_name = bottle_name[0] if bottle_name else ""

            if not program_path or not bottle_name:
                return {"jsonrpc": "2.0", "id": req_id,
                        "error": {"code": -32602, "message": "program_path and bottle_name required"}}

            if not create_bottle(bottle_name):
                return {"jsonrpc": "2.0", "id": req_id,
                        "error": {"code": -32000, "message": "Failed to create bottle"}}

            def bg():
                sanitize_bottle_env(bottle_name)
                for c in ["dxvk", "vcrun2019", "d3dx9"]:
                    install_bottle_dependency(bottle_name, c)
                res = run_wine_dependency_solver(program_path, bottle_name)
                if res["success"]:
                    for d in sorted({*res["dependencies"]}):
                        install_bottle_dependency(bottle_name, d)
            threading.Thread(target=bg, daemon=True).start()
            return {"jsonrpc": "2.0", "id": req_id,
                    "result": {"content": f"Bottle '{bottle_name}' created – setup running in background",
                               "contentType": "text/plain"}}

        # ---------- analyze_dependencies ---------------------------
        if tool_name == "analyze_dependencies":
            program_path = args.get("program_path", "")
            if isinstance(program_path, list):
                program_path = program_path[0] if program_path else ""

            res = analyze_dependencies_static(program_path)
            if not res["success"] or not res["dependencies"]:
                res = run_wine_dependency_solver(program_path, "temp_analysis")

            if res["success"]:
                deps = res.get("dependencies", [])
                return {"jsonrpc": "2.0", "id": req_id,
                        "result": {"content": f"Found {len(deps)} dependencies:\n" + "\n".join(deps),
                                   "contentType": "text/plain"}}
            return {"jsonrpc": "2.0", "id": req_id,
                    "error": {"code": -32000, "message": res.get("error", "unknown error")}}

        # ---------- bottles_install_deps ---------------------------
        if tool_name == "bottles_install_deps":
            program_path = args.get("program_path") or args.get("exe_path")
            bottle_name = args.get("bottle_name")

            # Normalisierung: List -> str
            if isinstance(program_path, list):
                program_path = program_path[0] if program_path else ""
            if isinstance(bottle_name, list):
                bottle_name = bottle_name[0] if bottle_name else ""

            if not program_path or not bottle_name:
                return {"jsonrpc": "2.0", "id": req_id,
                        "error": {"code": -32602, "message": "program_path and bottle_name required"}}

            def bg():
                res = analyze_dependencies_static(program_path)
                if not res.get("dependencies"):
                    res = run_wine_dependency_solver(program_path, bottle_name)
                if res["success"]:
                    for d in sorted({*res["dependencies"]}):
                        install_bottle_dependency(bottle_name, d)
            threading.Thread(target=bg, daemon=True).start()
            return {"jsonrpc": "2.0", "id": req_id,
                    "result": {"content": f"Scan started for '{program_path}'",
                               "contentType": "text/plain"}}

        # ---------- unknown tool -------------------------------
        return {"jsonrpc": "2.0", "id": req_id,
                "error": {"code": -32601, "message": f"Tool not found: {tool_name}"}}

    # ---- unknown method ---------------------------------------
    return {"jsonrpc": "2.0", "id": req_id,
            "error": {"code": -32601, "message": f"Method not supported: {method}"}}


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "name": "BottleAutomator",
        "version": "2.0.0",
        "status": "ready"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8766)