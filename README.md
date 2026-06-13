# AUDIT-VIEWER

[日本語版 README はこちら / Japanese README](README_ja.md)

A local GUI tool to **run, browse, and compare** results from
[claude-audit](../claude-audit) and [codex-audit](../codex-audit).
Its goal is unified management of local security audits across AI coding agents
from different vendors, using a common output schema.

> **Unofficial project.** Not affiliated with Anthropic or OpenAI.

## Features

- **Python standard library only** — no pip install; just `python3 audit_viewer.py`
- **English / Japanese UI** — defaults to English; toggle to Japanese with the button in the header (choice is persisted in the browser)
- **Local only** — binds to 127.0.0.1; audit data never leaves your machine
- **Snapshot management** — results are saved as `snapshots/<tool>_<UTC timestamp>.json` (mode 600)
- **Configurable via .env** — audit script locations, port, and snapshot directory
- **Extensible** — any audit script that follows the common schema can be registered with one line

## What it does

### 1. Run audits
Pick a tool and press "Run". The registered audit script is executed with `--json`
and the result is saved as a timestamped snapshot.

### 2. Browse
Click a snapshot to see:
- WARN / REVIEW / INFO summary cards
- A findings table with severity filters
- Tabbed inventory views (MCP servers, projects, hooks, plugins, automations, skills, retention, etc.)

### 3. Compare over time
Select two snapshots from the same tool to see a diff:
- Summary count deltas (+/-)
- Added (green) / removed (red) findings
- Inventory items added, removed, or **changed field-by-field**
  (e.g. old and new values shown side by side when an MCP server's command or env changes)

New MCP servers, newly trusted projects, hook changes — drift since your last audit
is visible at a glance.

## Install & run

```sh
cp .env.sample .env     # then edit paths to match your environment
python3 audit_viewer.py                       # opens your browser
python3 audit_viewer.py --no-browser --port 8765
python3 audit_viewer.py --snapshots-dir /path/to/snapshots
```

On Windows, use `python audit_viewer.py` (or `py -3 audit_viewer.py`) from
PowerShell.

If no `.env` exists, the defaults assume the audit tools live in sibling
directories (`../claude-audit`, `../codex-audit`). The viewer automatically
uses the PowerShell scripts on Windows and the zsh scripts on macOS.

> On macOS, if the system python3 fails due to an unaccepted Xcode license,
> use `/opt/homebrew/bin/python3 audit_viewer.py` or run `sudo xcodebuild -license`.

## Configuration (.env)

| Key | Default | Description |
|---|---|---|
| `CLAUDE_AUDIT_SCRIPT` | OS-specific sibling script | Path to claude-audit |
| `CODEX_AUDIT_SCRIPT` | OS-specific sibling script | Path to codex-audit |
| `SNAPSHOTS_DIR` | `snapshots` | Snapshot storage directory |
| `PORT` | `8765` | HTTP port (overridable with `--port`) |
| `TOOL_<ID>` | — | Register an additional tool: `<label>:<script_path>` |

Relative paths are resolved from the audit-viewer directory.

## Layout

```
audit-viewer/
├── audit_viewer.py   # HTTP server + audit runner + diff engine
├── index.html        # single-page GUI
├── .env.sample       # configuration template (copy to .env)
├── snapshots/        # saved audit results (keep out of git)
└── README.md
```

## Adding more audit tools

To integrate another vendor's audit program, add one line to `.env`:

```ini
TOOL_GEMINI=gemini-audit:../gemini-audit/gemini_audit.sh
```

The only requirement on the audit script is that `--json` emits the **common schema**:

```json
{
  "timestamp": "...", "hostname": "...", "username": "...",
  "summary": { "warn": 0, "review": 0, "info": 0 },
  "findings": [ { "severity": "WARN|REVIEW|INFO", "section": "...", "message": "...", "detail": "..." } ]
}
```

Any additional top-level arrays of objects automatically appear as tabs in the
browse view. To include a section in diffs, register its identity fields in
`INVENTORY_KEYS` in `audit_viewer.py`.

## API

| Method | Path | Description |
|---|---|---|
| GET | `/api/tools` | Registered tools and availability |
| GET | `/api/snapshots` | List snapshots |
| GET | `/api/snapshot?file=NAME` | Snapshot contents |
| GET | `/api/diff?old=A&new=B` | Diff two snapshots (same tool only) |
| POST | `/api/run` `{"tool":"claude"}` | Run an audit and save the snapshot |
| POST | `/api/snapshot/delete` `{"file":NAME}` | Delete a snapshot |

## Requirements

- Python 3.9+ (standard library only)
- Windows PowerShell 5.1+ or PowerShell 7+ on Windows
- See each audit tool's README for its platform-specific requirements

## Security notes

- Snapshots contain environment details (config paths, project lists).
  Keep `snapshots/` in `.gitignore` and never commit them.
- The server has no authentication; it is a local development tool.
  Do not bind it to anything other than 127.0.0.1.

## License

MIT
