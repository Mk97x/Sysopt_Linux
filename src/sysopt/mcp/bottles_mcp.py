#!/usr/bin/env python3
"""
Bottles-MCP-Server v4
- Deterministic EXE enumeration & scoring (now scoped to subpath)
- Candidates limited to relevant game folder 
- Shortcut creation via bottles-cli in correct context (cwd=drive_c + WINEPREFIX)
- New tool: bottles_folder_installer for pre-installed folders
- Robust error handling and logging
- Live Feedback via Ollama API
"""

from __future__ import annotations

import os
import subprocess
import json
import re
import threading
import time
import shutil
import difflib
from pathlib import Path
from typing import Optional, Set, List, Dict, Any
from shutil import which
from collections import defaultdict

from contextlib import contextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .dll_map import DLL_MAP
from .dep_scanner import scan_deps_static, scan_deps_wine

from .bottles_handler import create_bottle, copy_folder_to_bottle, wait_until_wineserver_idle, install_dep, create_shortcut_in_bottle, log_status, BOTTLE_STATUS, prefix_path, WINE_CMD, WINEDUMP
from .exe_handler import probe_pe_metadata, enumerate_and_score_exes
from .iso_handler import find_setup_exe_in_iso, run_setup_in_bottle, mount_iso

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------
@app.get("/status/{bottle_name}")
async def get_bottle_status(bottle_name: str):
    data = BOTTLE_STATUS[bottle_name]
    candidates = data.get("candidates", [])
    candidates_short = [
        {"path": c.get("path"), "score": c.get("score"), "product_name": c.get("product_name"), "size": c.get("size"), "mtime": c.get("mtime")}
        for c in candidates
    ]
    return {
        "bottle": bottle_name,
        "status": data.get("status", "idle"),
        "log": data.get("log", []),
        "candidates": candidates_short
    }

@app.get("/candidates/{bottle_name}")
async def get_candidates(bottle_name: str):
    if not bottle_name:
        raise HTTPException(status_code=400, detail="bottle_name required")

    subpath = BOTTLE_STATUS[bottle_name].get("subpath")
    existing = BOTTLE_STATUS[bottle_name].get("candidates")
    if existing:
        trimmed = [
            {"path": c["path"], "score": c["score"], "product_name": c.get("product_name", ""), "size": c.get("size"), "mtime": c.get("mtime")}
            for c in existing
        ]
        return {"bottle": bottle_name, "candidates": trimmed}

    candidates = enumerate_and_score_exes(bottle_name, top_n=10, subpath=subpath)
    BOTTLE_STATUS[bottle_name]["candidates"] = candidates
    log_status(bottle_name, f"[MCP] Enumerated {len(candidates)} EXE candidates (subpath={subpath})")
    trimmed = [
        {"path": c["path"], "score": c["score"], "product_name": c.get("product_name", ""), "size": c.get("size"), "mtime": c.get("mtime")}
        for c in candidates
    ]
    return {"bottle": bottle_name, "candidates": trimmed}

@app.post("/agent/choose_exe")
async def agent_choose_exe(payload: Request):
    data = await payload.json()
    bottle = data.get("bottle")
    exe_path = data.get("exe_path")
    create_shortcut = data.get("create_shortcut", False)
    create = data.get("create_bottle", False)

    if not bottle or not exe_path:
        raise HTTPException(status_code=400, detail="bottle and exe_path required")

    def bg_scan():
        try:
            log_status(bottle, f"[MCP] Processing EXE: {exe_path} (create_shortcut={create_shortcut})")
            if create and not prefix_path(bottle).exists():
                if not create_bottle(bottle):
                    log_status(bottle, "[MCP] create_bottle failed")
                    return

            candidates = enumerate_and_score_exes(bottle, top_n=50, subpath=BOTTLE_STATUS[bottle].get("subpath"))
            BOTTLE_STATUS[bottle]["candidates"] = candidates

            exe_p = Path(exe_path)
            if not exe_p.exists():
                matched = next((Path(c["path"]) for c in candidates if Path(c["path"]).name.lower() == exe_p.name.lower()), None)
                if not matched:
                    log_status(bottle, f"[ERROR] EXE not found: {exe_path}")
                    return
                exe_p = matched
                log_status(bottle, f"[MCP] Matched to: {exe_p}")

            res = scan_deps_static(str(exe_p), winedump_cmd=WINEDUMP)
            deps = set(res.get("dependencies", []))
            if not deps:
                log_status(bottle, "[MCP] Static scan found no deps, falling back to wine runtime scan")
                res2 = scan_deps_wine(program=str(exe_p), wineprefix=str(prefix_path(bottle)), wine_cmd=WINE_CMD, timeout=20)
                deps = set(res2.get("dependencies", []))

            if deps:
                log_status(bottle, f"[MCP] Installing {len(deps)} dependencies")
                for d in sorted(deps):
                    install_dep(bottle, d)
            else:
                log_status(bottle, "[MCP] No dependencies detected")

            if create_shortcut:
                create_shortcut_in_bottle(bottle, exe_p)

            log_status(bottle, f"[MCP] Completed processing for {exe_p}")

        except Exception as e:
            log_status(bottle, f"[FATAL] Exception in choose_exe: {e}")

    threading.Thread(target=bg_scan, daemon=True).start()
    return {"status": "started", "bottle": bottle, "exe_path": exe_path, "create_shortcut": create_shortcut}

# ------------------------------------------------------------------
# JSON-RPC MCP Protocol
# ------------------------------------------------------------------
@app.post("/")
async def handle(request: Request):
    body = await request.json()
    method, req_id = body.get("method"), body.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "BottleAutomator", "version": "4.0.0"},
                "capabilities": {"tools": {}, "resources": {}, "prompts": {}}
            }
        }

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [
                    {
                        "name": "bottles_installer",
                        "description": "Full installation using Bottles (EXE or ISO).",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "program_path": {"type": "string"},
                                "bottle_name": {"type": "string"}
                            },
                            "required": ["program_path", "bottle_name"]
                        }
                    },
                    {
                        "name": "bottles_folder_installer",
                        "description": "Copies a host folder into a new or existing bottle, scans for EXEs, and prepares candidates for dependency installation and shortcut creation.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "host_folder": {"type": "string"},
                                "bottle_name": {"type": "string"},
                                "target_subdir": {"type": "string"}
                            },
                            "required": ["host_folder", "bottle_name"]
                        }
                    }
                ]
            }
        }

    if method in ("call", "tools/call"):
        params = body.get("params", {})
        tool = params.get("name") or params.get("toolName")
        if isinstance(tool, list) and tool:
            tool = str(tool[0]) if tool[0] else ""
        args = params.get("arguments") or params

        if tool == "bottles_installer":
            exe, bottle = args.get("program_path"), args.get("bottle_name")
            if not exe or not bottle:
                return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32602, "message": "program_path and bottle_name required"}}

            def bg():
                exe_input = args.get("program_path")
                bottle = args.get("bottle_name")
                actual_exe = None

                try:
                    if Path(exe_input).suffix.lower() == ".iso":
                        log_status(bottle, f"[MCP] Detected ISO file: {exe_input}")
                        if not prefix_path(bottle).exists():
                            if not create_bottle(bottle):
                                return
                        else:
                            log_status(bottle, f"[MCP] Using existing bottle: {bottle}")

                        installer_dest = prefix_path(bottle) / "drive_c" / "installer"
                        installer_dest.mkdir(parents=True, exist_ok=True)

                        with mount_iso(exe_input, target_dir=installer_dest) as mount_point:
                            setup_exe = find_setup_exe_in_iso(mount_point)
                            if not setup_exe:
                                log_status(bottle, f"[ERROR] No setup/install EXE found in ISO: {exe_input}")
                                return
                            actual_exe = str(setup_exe)

                            res = scan_deps_wine(
                                program=actual_exe,
                                wineprefix=str(prefix_path(bottle)),
                                wine_cmd=WINE_CMD,
                                timeout=10
                            )
                            if not res["success"]:
                                log_status(bottle, "[MCP] Falling back to static scan")
                                res = scan_deps_static(program=actual_exe, winedump_cmd=WINEDUMP)

                            for dep in sorted(set(res.get("dependencies", []))):
                                install_dep(bottle, dep)

                    else:
                        actual_exe = exe_input
                        if not create_bottle(bottle):
                            return

                        exe_path = Path(actual_exe)
                        if not exe_path.is_relative_to(prefix_path(bottle)):
                            temp_dest = prefix_path(bottle) / "drive_c" / "temp_installer"
                            temp_dest.mkdir(parents=True, exist_ok=True)
                            exe_name = exe_path.name
                            target_exe = temp_dest / exe_name
                            shutil.copy(exe_path, target_exe)
                            actual_exe = str(target_exe)

                        res = scan_deps_wine(
                            program=actual_exe,
                            wineprefix=str(prefix_path(bottle)),
                            wine_cmd=WINE_CMD,
                            timeout=10
                        )
                        if not res["success"]:
                            log_status(bottle, "[MCP] Falling back to static scan")
                            res = scan_deps_static(program=actual_exe, winedump_cmd=WINEDUMP)

                        for dep in sorted(set(res.get("dependencies", []))):
                            install_dep(bottle, dep)

                    host_exe_path = Path(actual_exe)
                    log_status(bottle, f"[MCP] Running installer via Bottles: {host_exe_path}")
                    run_setup_in_bottle(bottle, host_exe_path)

                    candidates = enumerate_and_score_exes(bottle, top_n=10)
                    BOTTLE_STATUS[bottle]["candidates"] = candidates
                    log_status(bottle, f"[MCP] Found {len(candidates)} EXE candidates after install")
                    log_status(bottle, f"[MCP] Background process for bottle '{bottle}' completed.")

                except Exception as e:
                    log_status(bottle, f"[FATAL] Exception in background task: {e}")

            threading.Thread(target=bg, daemon=True).start()
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Bottle '{bottle}' created – setup running in background. Call /candidates/{bottle} to see EXE candidates after install."
                        }
                    ]
                }
            }

        if tool == "bottles_folder_installer":
            host_folder = args.get("host_folder")
            bottle = args.get("bottle_name")
            target_subdir = args.get("target_subdir") or Path(host_folder).name
            target_subdir = target_subdir.replace(" ", "-")

            if not host_folder or not bottle:
                return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32602, "message": "host_folder and bottle_name required"}}

            def bg():
                try:
                    if not prefix_path(bottle).exists():
                        if not create_bottle(bottle):
                            log_status(bottle, "[ERROR] Failed to create bottle")
                            return

                    if not copy_folder_to_bottle(bottle, host_folder, target_subdir):
                        log_status(bottle, "[ERROR] Folder copy failed")
                        return

                    BOTTLE_STATUS[bottle]["subpath"] = target_subdir
                    candidates = enumerate_and_score_exes(bottle, top_n=10, subpath=target_subdir)
                    BOTTLE_STATUS[bottle]["candidates"] = candidates
                    log_status(bottle, f"[MCP] Found {len(candidates)} EXE candidates after folder copy")

                except Exception as e:
                    log_status(bottle, f"[FATAL] Exception in bottles_folder_installer: {e}")

            threading.Thread(target=bg, daemon=True).start()
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{
                        "type": "text",
                        "text": f"Folder '{host_folder}' copied to bottle '{bottle}'. Call /candidates/{bottle} to choose EXE for dependency scan and shortcut creation."
                    }]
                }
            }

        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Tool not found: {tool}"}}

    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method not supported: {method}"}}

@app.get("/")
async def root():
    return {
        "name": "BottleAutomator",
        "version": "4.0.0",
        "installation_type": INSTALL_TYPE,
        "status": "ready"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8766)