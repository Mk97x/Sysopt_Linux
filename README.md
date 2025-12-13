

# 🧠 SysOpt – AI-Powered Windows Software Installer for Linux (via Bottles)

> **Install Windows apps and games on Linux with natural language — no Wine knowledge required.**  
> AI-driven automation with Ollama, Bottles, and MCP — powered by your local LLM.



## ✨ Core Features

- **Natural Language Installation**  
  Type prompts like _“Install Hogs of War from /mnt/data/PROJEKT”_ → AI auto-selects installer type.
  
- **Smart Installer Selection**  
  - 📦 `bottles_installer` → triggered for **files** (`.exe`, `.iso`)  
  - 📁 `bottles_folder_installer` → triggered for **folders** (pre-extracted games, GOG installs)  
  *No manual tool selection needed.*

- **Full System Insights**  
  Scan RAM, storage, ports, autoruns, and CVEs — all via API.

- **Automated Dependency Resolution**  
  Scans EXEs for missing DLLs (`vcrun2019`, `dxvk`, `d3dcompiler`) → installs automatically.

- **Reliable Shortcut Creation**  
  - Auto-created shortcuts for EXE/ISO installs (via Bottles)  
  - Manual YAML-based shortcuts for folder installs (avoids Bottles’ broken internal shortcuts)

- **Web-Based Setup UI**  
  Configure paths, Ollama, and MCP server in one click — with auto-restart.

- **100% Local & Private**  
  No cloud APIs. Everything runs on your machine.

---

## 🚀 Quick Start

### Prerequisites

- Linux (Ubuntu, Pop!_OS, CachyOS)
- [Bottles](https://usebottles.com) (Flatpak recommended)
- [Ollama](https://ollama.com) (`llama3.2`, `mistral`, etc.)
- Python 3.10+

### Installation

```bash
git clone https://github.com/yourusername/sysopt.git
cd sysopt
pip install -r requirements.txt
```

### Configuration

1. Open your browser:  
   → Visit `http://localhost:8000/setup`

2. Fill in:
   - `PREFIX`: Path to your Bottles folder (e.g., `/mnt/data`)
   - `OLLAMA_HOST`: `localhost`
   - `OLLAMA_MODEL`: `llama3.2`
   - `MCP_SERVER_IP`: `127.0.0.1`

3. Click **Save Configuration and Restart**

> 💡 `.env` is saved in the project root. Your settings persist across restarts.

### Run

```bash
python -m app.main
```

Open `http://localhost:8000/agent` to start chatting with your AI agent.

---

## 💬 Example Prompts (AI Agent)

### ✅ **Folder Install (Pre-Extracted Games)**  
*Triggers `bottles_folder_installer`*

> `"Install Hogs of War from /mnt/data/Hogs of War 2.0"`  
> `"Set up F.E.A.R. Platinum Collection from /mnt/data/FEAR"`  
> `"Copy the folder /mnt/data/PROJEKT/DeadSpace to a new bottle named Dead Space"`

→ AI detects **folder path** → uses `bottles_folder_installer` → copies folder → scans for `.exe` → creates shortcut.

---

### ✅ **File Install (EXE or ISO)**  
*Triggers `bottles_installer`*

> `"Install /mnt/data/PROJEKT/Dead.Space/DeadSpace.iso"`  
> `"Run setup_hogs_of_war_2.0.0.6.exe in a new bottle called Hogs of War"`  
> `"Install GOG’s C&C Red Alert 2 from /mnt/data/CNC95/setup.exe"`

→ AI detects **file extension** (`.exe`, `.iso`) → uses `bottles_installer` → mounts ISO or copies EXE → runs installer → auto-generates Bottles shortcut.

---

### ❌ Avoid These (They’ll Fail)

> `"Install the folder /mnt/data/PROJEKT/Dead.Space/DeadSpace.iso"`  
> → AI might misinterpret `.iso` as folder → uses wrong tool → fails.

> `"Install /mnt/data/PROJEKT/Dead.Space/ from the folder"`  
> → AI might think it’s a file → fails.

✅ **Always be clear**:  
- Use **folder paths** → for **extracted games**  
- Use **file paths** → for **installers (.exe, .iso)**
- **Bottle name** is not required but recommended since LLMs get creative with symbols and Linux can't always handle that out of the box.
---

## 🛠️ How It Works

```
User (Chat UI)
      ↓
[Flask API] ←→ [Ollama (LLM)]
      ↓
[MCP Server] ←→ [Bottles (Wine)]
      ↓
Host Filesystem (Games, Installers, .env)
```

| Component | Role |
|----------|------|
| **Flask** | Web server + API + setup UI |
| **Ollama** | Local LLM that interprets prompts and selects tools |
| **MCP Server** | Executes Bottles commands: install, copy, scan, shortcut |
| **Bottles** | Isolated Wine environments (Flatpak) |
| **.env** | Stores configuration (PREFIX, Ollama, ports) |
| **bottle.yml** | Stores manual shortcuts for folder installs |

---

## 🧩 Tool Selection Logic (AI Rules)

The AI uses **file extension and context** to choose the right tool:

| Input | AI Chooses | Why |
|-------|------------|-----|
| `/mnt/data/Game/` (folder) | `bottles_folder_installer` | Folder path → likely pre-extracted game |
| `/mnt/data/Game/setup.exe` | `bottles_installer` | `.exe` → installer |
| `/mnt/data/Game.iso` | `bottles_installer` | `.iso` → mounted installer |
| `/mnt/data/Game/` + “run the .exe inside” | `bottles_folder_installer` | Context: folder → extract → scan → install |

> ✅ **No manual tool selection needed** — the AI understands intent.

---

## 📁 Project Structure

```
sysopt/
├── app/
│   ├── main.py              ← Flask app entrypoint
│   └── .env                 ← Auto-generated config
├── api/
│   └── api.py               ← API routes (scanners, agent, MCP proxy)
├── mcp/
│   └── bottles_mcp.py       ← MCP server (FastAPI)
├── webui/
│   ├── templates/
│   │   ├── index.html
│   │   ├── setup.html
│   │   ├── scan.html
│   │   └── agent.html
│   └── static/
│       └── css/
├── scanner/
│   ├── ram_cpu.py
│   ├── storage.py
│   ├── autorun.py
│   ├── ports.py
│   └── cve.py
├── bottles_handler.py       ← Bottles CLI wrapper
├── exe_handler.py           ← EXE metadata scanner
├── dll_map.py               ← DLL → Winetricks mapping
├── requirements.txt
└── README.md
```

---

## ⚙️ Environment Variables

| Variable | Default | Description |
|---------|---------|-------------|
| `PREFIX` | *(required)* | Path to Bottles root (e.g., `/mnt/data`) |
| `OLLAMA_HOST` | `localhost` | Ollama server host |
| `OLLAMA_PORT` | `11434` | Ollama API port |
| `OLLAMA_MODEL` | `llama3.2` | LLM model to use |
| `MCP_SERVER_IP` | `127.0.0.1` | MCP server IP |
| `MCP_SERVER_PORT` | `8766` | MCP JSON-RPC port |
| `WEBUI_PORT` | `8000` | Flask web server port |

> Configure via `/setup` → changes auto-save to `.env` → app restarts.

---

## 🛡️ Security Notes

- All data stays local — no cloud calls.
- MCP server binds to `127.0.0.1` by default.
- The setup UI (`/setup`) should be **disabled in production** or protected with auth.
- Bottles runs in Flatpak sandbox — isolates Windows apps from your system.

---

## 🧪 Testing Tips

| Task | Command |
|------|---------|
| Check Bottle list | `flatpak run --command=bottles-cli com.usebottles.bottles list` |
| Start MCP manually | `python -m mcp.bottles_mcp` |
| Test Ollama | `curl http://localhost:11434/api/generate -d '{"model":"llama3.2","prompt":"hi"}'` |
| View `.env` | `cat .env` |


---

## 💬 Contact

Built by **Mk97x**  
For questions or suggestions: open an [Issue](https://github.com/yourusername/sysopt/issues)





