#!/usr/bin/env python3
"""AUDIT-VIEWER - Local GUI for claude-audit / codex-audit results.

Run audits, save timestamped snapshots, and diff any two snapshots.
Localhost-only HTTP server, stdlib only. Usage:

    python3 audit_viewer.py [--port 8765] [--snapshots-dir DIR]
"""
import argparse
import json
import os
import re
import subprocess
import sys
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

BASE_DIR = Path(__file__).resolve().parent


def load_env(path):
    """Parse a simple KEY=VALUE .env file (no quoting rules, # comments)."""
    env = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        env[key.strip()] = val.strip().strip('"').strip("'")
    return env


ENV = load_env(BASE_DIR / ".env")


def _resolve(p, default):
    raw = ENV.get(p, "") or default
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (BASE_DIR / path).resolve()


SNAP_DIR = _resolve("SNAPSHOTS_DIR", "snapshots")
DEFAULT_PORT = int(ENV.get("PORT", "8765"))

# Tool registry: id -> {label, script}.
# Built-in tools can be re-pathed via CLAUDE_AUDIT_SCRIPT / CODEX_AUDIT_SCRIPT in .env.
# Additional vendors: add TOOL_<id>=<label>:<script_path> lines to .env.
TOOLS = {
    "claude": {
        "label": "claude-audit",
        "script": _resolve("CLAUDE_AUDIT_SCRIPT", "../claude-audit/claude_audit.sh"),
    },
    "codex": {
        "label": "codex-audit",
        "script": _resolve("CODEX_AUDIT_SCRIPT", "../codex-audit/codex_audit.sh"),
    },
}
for _k, _v in ENV.items():
    if _k.startswith("TOOL_") and ":" in _v:
        _label, _, _path = _v.partition(":")
        _tid = _k[len("TOOL_"):].lower()
        _p = Path(_path).expanduser()
        TOOLS[_tid] = {
            "label": _label,
            "script": _p if _p.is_absolute() else (BASE_DIR / _p).resolve(),
        }

SNAP_NAME_RE = re.compile(r"^([a-z0-9][a-z0-9-]*)_(\d{8}T\d{6}Z)\.json$")


# ---------------------------------------------------------------- helpers

def list_snapshots():
    snaps = []
    for f in sorted(SNAP_DIR.glob("*.json")):
        m = SNAP_NAME_RE.match(f.name)
        if not m:
            continue
        try:
            data = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        summary = data.get("summary", {}) if isinstance(data, dict) else {}
        snaps.append({
            "file": f.name,
            "tool": m.group(1),
            "taken_at": m.group(2),
            "timestamp": data.get("timestamp", "") if isinstance(data, dict) else "",
            "hostname": data.get("hostname", "") if isinstance(data, dict) else "",
            "username": data.get("username", "") if isinstance(data, dict) else "",
            "summary": summary,
        })
    snaps.sort(key=lambda s: s["taken_at"], reverse=True)
    return snaps


def load_snapshot(name):
    if not SNAP_NAME_RE.match(name):
        raise ValueError("invalid snapshot name")
    p = SNAP_DIR / name
    return json.loads(p.read_text())


def run_audit(tool):
    cfg = TOOLS.get(tool)
    if not cfg:
        raise ValueError(f"unknown tool: {tool}")
    script = cfg["script"]
    if not script.exists():
        raise FileNotFoundError(f"audit script not found: {script}")
    proc = subprocess.run(
        ["/bin/zsh", str(script), "--json"],
        capture_output=True, text=True, timeout=300,
    )
    if not proc.stdout.strip():
        raise RuntimeError(f"audit produced no output (exit {proc.returncode}): {proc.stderr[:500]}")
    data = json.loads(proc.stdout)
    # --all-users would produce an array; viewer handles single-user snapshots
    if isinstance(data, list):
        data = data[0]
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    fname = f"{tool}_{ts}.json"
    out = SNAP_DIR / fname
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    os.chmod(out, 0o600)
    return fname, data


# ---------------------------------------------------------------- diffing

# Per-tool keyed inventory sections: section -> (json key, key fields)
INVENTORY_KEYS = {
    "claude": {
        "mcp_servers": ("mcp_servers", ["name"]),
        "projects": ("projects", ["path"]),
        "hooks": ("hooks", ["event", "source", "command"]),
        "sensitive_files": ("sensitive_files", ["path"]),
    },
    "codex": {
        "mcp_servers": ("mcp_servers", ["name"]),
        "plugins": ("plugins", ["id"]),
        "apps": ("apps", ["id"]),
        "trusted_projects": ("trusted_projects", ["path"]),
        "automations": ("automations", ["id"]),
        "skills": ("skills", ["source", "name"]),
        "sensitive_files": ("sensitive_files", ["path"]),
    },
}


def item_key(item, fields):
    return " / ".join(str(item.get(f, "")) for f in fields)


def finding_key(f):
    return f"[{f.get('severity','')}] {f.get('section','')}: {f.get('message','')}" + \
        (f" — {f['detail']}" if f.get("detail") else "")


def diff_snapshots(old, new, tool):
    result = {"sections": [], "findings": {"added": [], "removed": []},
              "summary_old": old.get("summary", {}), "summary_new": new.get("summary", {})}

    # Findings diff (string-keyed)
    old_f = {finding_key(f) for f in old.get("findings", [])}
    new_f = {finding_key(f) for f in new.get("findings", [])}
    result["findings"]["added"] = sorted(new_f - old_f)
    result["findings"]["removed"] = sorted(old_f - new_f)

    # Inventory diffs
    for sect, (jkey, fields) in INVENTORY_KEYS.get(tool, {}).items():
        old_items = {item_key(i, fields): i for i in old.get(jkey, []) if isinstance(i, dict)}
        new_items = {item_key(i, fields): i for i in new.get(jkey, []) if isinstance(i, dict)}
        added = sorted(set(new_items) - set(old_items))
        removed = sorted(set(old_items) - set(new_items))
        changed = []
        for k in set(old_items) & set(new_items):
            if old_items[k] != new_items[k]:
                changes = {}
                for fk in set(old_items[k]) | set(new_items[k]):
                    ov, nv = old_items[k].get(fk), new_items[k].get(fk)
                    if ov != nv:
                        changes[fk] = {"old": ov, "new": nv}
                changed.append({"key": k, "changes": changes})
        if added or removed or changed:
            result["sections"].append({
                "section": sect, "added": added, "removed": removed,
                "changed": sorted(changed, key=lambda c: c["key"]),
            })
    return result


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = "AuditViewer/0.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("[%s] %s\n" % (datetime.now().strftime("%H:%M:%S"), fmt % args))

    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _err(self, msg, status=400):
        self._json({"error": str(msg)}, status)

    def do_GET(self):
        url = urlparse(self.path)
        q = parse_qs(url.query)
        try:
            if url.path == "/":
                body = (BASE_DIR / "index.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif url.path == "/api/tools":
                self._json({tid: {"label": t["label"], "available": t["script"].exists()}
                            for tid, t in TOOLS.items()})
            elif url.path == "/api/snapshots":
                self._json(list_snapshots())
            elif url.path == "/api/snapshot":
                self._json(load_snapshot(q["file"][0]))
            elif url.path == "/api/diff":
                a, b = q["old"][0], q["new"][0]
                ma, mb = SNAP_NAME_RE.match(a), SNAP_NAME_RE.match(b)
                if not (ma and mb):
                    return self._err("invalid snapshot name")
                if ma.group(1) != mb.group(1):
                    return self._err("snapshots are from different tools")
                self._json(diff_snapshots(load_snapshot(a), load_snapshot(b), ma.group(1)))
            else:
                self._err("not found", 404)
        except FileNotFoundError as e:
            self._err(e, 404)
        except Exception as e:  # noqa: BLE001 - surface to UI
            self._err(e, 500)

    def do_POST(self):
        url = urlparse(self.path)
        try:
            if url.path == "/api/run":
                length = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(length) or b"{}")
                tool = payload.get("tool", "")
                fname, data = run_audit(tool)
                self._json({"file": fname, "summary": data.get("summary", {})})
            elif url.path == "/api/snapshot/delete":
                length = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(length) or b"{}")
                name = payload.get("file", "")
                if not SNAP_NAME_RE.match(name):
                    return self._err("invalid snapshot name")
                (SNAP_DIR / name).unlink()
                self._json({"deleted": name})
            else:
                self._err("not found", 404)
        except Exception as e:  # noqa: BLE001
            self._err(e, 500)


def main():
    global SNAP_DIR
    ap = argparse.ArgumentParser(description="Audit viewer for claude-audit / codex-audit")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--snapshots-dir", default=str(SNAP_DIR))
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    SNAP_DIR = Path(args.snapshots_dir)
    SNAP_DIR.mkdir(parents=True, exist_ok=True)

    addr = ("127.0.0.1", args.port)
    httpd = ThreadingHTTPServer(addr, Handler)
    url = f"http://{addr[0]}:{addr[1]}/"
    print(f"AUDIT-VIEWER listening on {url}  (snapshots: {SNAP_DIR})")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
