from __future__ import annotations

import os
import subprocess
import re
import time
import difflib
from pathlib import Path
from typing import List, Dict, Any, Optional


from .bottles_handler import log_status, WINEDUMP, prefix_path

# ------------------------------------------------------------------
# EXE Metadata & Scoring (now supports subpath)
# ------------------------------------------------------------------
def probe_pe_metadata(exe_path: Path) -> Dict[str, str]:
    product_name = ""
    file_version = ""
    try:
        cmd = WINEDUMP + ["-jv", str(exe_path)]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        out = (res.stdout or "") + "\n" + (res.stderr or "")
        m = re.search(r"ProductName[:=]\s*(.+)", out, re.IGNORECASE)
        if m:
            product_name = m.group(1).strip().strip('"')
        m2 = re.search(r"FileVersion[:=]\s*(.+)", out, re.IGNORECASE)
        if m2:
            file_version = m2.group(1).strip().strip('"')
    except Exception:
        pass

    if not product_name:
        try:
            res2 = subprocess.run(["strings", str(exe_path)], capture_output=True, text=True, timeout=8)
            lines = res2.stdout.splitlines()
            for ln in lines[:400]:
                ln = ln.strip()
                if 3 <= len(ln) <= 64 and any(c.isalpha() for c in ln) and not ln.lower().startswith("c:\\"):
                    product_name = ln
                    break
        except Exception:
            pass

    return {"product_name": product_name, "file_version": file_version}

def enumerate_and_score_exes(bottle: str, top_n: int = 10, subpath: Optional[str] = None) -> List[Dict[str, Any]]:
    prefix = prefix_path(bottle)
    if not prefix.exists():
        log_status(bottle, "[DEBUG] Prefix does not exist")
        return []

    # set root for prefix
    if subpath:
        search_root = prefix / "drive_c" / subpath
        if not search_root.exists():
            log_status(bottle, f"[WARN] Subpath '{subpath}' does not exist. Scanning full prefix.")
            search_root = prefix
    else:
        search_root = prefix / "drive_c" #fallback

    log_status(bottle, f"[DEBUG] Scanning for EXEs in: {search_root}")

    exclude_dirs = {"windows", "system32", "syswow64", "temp_installer", "installer"}
    exclude_keywords = {
        "uninstall", "crash", "report", "update", "patch", "readme",
        "vcredist", "directx", "setup", "inst", "uninst"
    }
    folder_hint = Path(subpath).name.lower() if subpath else bottle.lower().replace("-", "").replace("_", "").replace(" ", "")

    candidates = []
    found_exe_count = 0

    for root, dirs, files in os.walk(search_root):
        if any(ex in root.lower() for ex in exclude_dirs):
            log_status(bottle, f"[DEBUG] Skipping excluded dir: {root}")
            continue
        for f in files:
            if not f.lower().endswith(".exe"):
                continue
            found_exe_count += 1
            log_status(bottle, f"[DEBUG] Found EXE: {root}/{f}")

            name_noext = f[:-4].lower()
            if any(bad in name_noext for bad in exclude_keywords):
                log_status(bottle, f"[DEBUG] Skipping (excluded keyword): {f}")
                continue

            p = Path(root) / f
            try:
                stat = p.stat()
            except Exception:
                continue
            size = stat.st_size
            mtime = stat.st_mtime

            meta = probe_pe_metadata(p)
            prod_name = (meta.get("product_name") or "").strip()
            file_version = meta.get("file_version") or ""

            sim_name = difflib.SequenceMatcher(None, folder_hint, name_noext.replace(" ", "")).ratio()
            sim_prod = 0.0
            if prod_name:
                sim_prod = difflib.SequenceMatcher(None, folder_hint, prod_name.lower().replace(" ", "")).ratio()

            score = 0
            score += int(sim_name * 40)
            score += int(sim_prod * 30)
            if any(sub in root.lower() for sub in ("bin", "binaries", "win64", "win32", "program files")):
                score += 10
            if size > 2 * 1024 * 1024:
                score += 6
            if size > 20 * 1024 * 1024:
                score += 4
            age_days = (time.time() - mtime) / (60 * 60 * 24)
            if age_days < 30:
                score += 3
            elif age_days < 180:
                score += 1

            candidates.append({
                "path": str(p),
                "score": score,
                "sim_name": round(sim_name, 3),
                "sim_prod": round(sim_prod, 3),
                "product_name": prod_name,
                "file_version": file_version,
                "size": size,
                "mtime": mtime
            })

    candidates.sort(key=lambda x: (x["score"], x["sim_prod"], x["sim_name"], x["mtime"]), reverse=True)
    return candidates[:top_n]