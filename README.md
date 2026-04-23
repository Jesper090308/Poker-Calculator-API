# Pokerbot Workbench

A heads-up poker decision engine with a local web UI, session tracking, and optional OpenSpiel integration.

## What You Get

- Browser-based UI for hero cards, board texture, pot pressure, and villain tendencies
- Fast local decision engine with session history stored in SQLite
- Optional OpenSpiel support when a compatible environment is available
- A Windows launcher path that can be packaged into a simple `.exe`

## Run It Locally

From PowerShell:

```powershell
.\scripts\start.ps1
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000).

If you prefer direct Python for development:

```powershell
C:\Users\jespe\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe .\run_server.py
```

`run_server.py` keeps auto-reload on by default outside packaged builds.

## Build a Windows App

The project includes a launcher that starts the local server and opens the browser automatically. Build it with:

```powershell
.\scripts\build_exe.cmd
```

After a successful build, the executable will be at `dist\Pokerbot.exe`.

If your PowerShell execution policy blocks local scripts, the `.cmd` wrapper handles the bypass for this build step.

What the executable does:

- starts Pokerbot on `http://127.0.0.1:8000`
- opens the UI in the default browser
- keeps running until the user closes the executable window

Packaged builds store their local database in `%LOCALAPPDATA%\Pokerbot\data\pokerbot.db` by default, so user data is kept out of the temporary PyInstaller extraction folder.

## GitHub Setup

This repo is now structured to publish cleanly:

- local virtual environments and caches are ignored
- build output is ignored
- GitHub Actions workflows are included for tests and Windows builds

Suggested publishing flow:

1. Create a new empty GitHub repository.
2. Pick a license before publishing if you want others to reuse the code.
3. Run the usual Git commands locally:

```powershell
git init
git add .
git commit -m "Initial release"
git branch -M main
git remote add origin https://github.com/<your-user>/<your-repo>.git
git push -u origin main
```

If you prefer a GUI, GitHub Desktop works fine too.

## GitHub Actions

Two workflows are included:

- `ci.yml` runs the unit tests on pushes and pull requests
- `windows-exe.yml` builds `Pokerbot.exe` on demand and uploads it as a workflow artifact

That gives you a nice release flow:

1. Push the repo to GitHub.
2. Open the Actions tab.
3. Run the `Build Windows EXE` workflow manually.
4. Download the generated `Pokerbot.exe` artifact and share it with users.

## Project Layout

- `app/main.py`: FastAPI app and routes
- `app/engines/decision.py`: heuristic poker decision engine
- `app/engines/openspiel_adapter.py`: OpenSpiel detection and integration seam
- `app/services/game_store.py`: SQLite-backed session state
- `app/templates/index.html`: UI markup
- `app/static/`: CSS and browser JavaScript
- `run_server.py`: development server entry point
- `launch_pokerbot.py`: end-user launcher for local and packaged builds
- `scripts/build_exe.ps1`: PyInstaller build script
- `scripts/build_exe.cmd`: Windows-friendly wrapper for the build script

## Notes

- Heads-up play is the primary target.
- OpenSpiel remains optional and environment-dependent.
- The included tests run against the heuristic engine and local database path.
