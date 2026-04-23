# Pokerbot Workbench

A heads-up poker decision engine with a local web UI, session tracking, and optional OpenSpiel integration.

---

##  Features

-  Real-time poker decision engine (heads-up focus)
-  Browser-based UI for inputs like:
  - Hero cards
  - Board texture
  - Pot size & pressure
  - Villain tendencies
-  Session tracking using SQLite
-  Fast local server (auto-reload in dev mode)
-  Optional OpenSpiel integration (if available)
-  Windows executable build support

---

##  Run Locally

### Option 1: PowerShell (recommended)

```bash
.\scripts\start.ps1
```
## Then open:

`http://127.0.0.1:8000` or `localhost:8000`

### Option 2: Direct Python (development)
```bash
C:\Users\<your-user>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe .\run_server.py
```
## Development Mode

`run_server.py` runs with auto-reload enabled for fast iteration.

## Build Windows Executable

Create a standalone .exe:
```bash
.\scripts\build_exe.cmd
```
After building, the output will be:
```bash
dist\Pokerbot.exe
```
What the executable does:
Starts local server at `http://127.0.0.1:8000`
Opens the UI in your default browser
Runs until the window is closed

## GitHub Actions

This project includes:

CI pipeline: runs tests on every push / pull request
Windows build pipeline: generates `Pokerbot.exe` automatically

You can manually run builds from the GitHub Actions tab and download the artifact.
