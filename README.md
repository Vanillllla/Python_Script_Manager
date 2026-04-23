# Python Script Manager

Python Script Manager (`pysm`) is a Windows-focused local service for managing multiple Python scripts from a single web UI and CLI.

## Features

- Run Python scripts as managed subprocesses without opening extra terminal windows.
- Open an embedded browser console for every running script and interact with `stdin/stdout`.
- Discover local Python interpreters and create managed virtual environments inside the app folder.
- Inspect installed modules, detect missing imports, and offer installation into the selected environment.
- Pause, resume, stop, and restart scripts from CLI or web UI.
- Monitor system and per-script CPU / memory usage.
- Configure manager autostart and script autostart.

## Console Backend

The default interactive console backend is a hidden pipe-based subprocess session because it is the most reliable option for normal Python scripts that use `print()` and `input()` on Windows 10/11 without opening a new terminal window.

The codebase also includes a Windows `ConPTY` path through `pywinpty`. If you want to experiment with it, start the manager with `PYSM_CONSOLE_BACKEND=conpty`.

## Quick Start

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e .[dev]
.venv\Scripts\pysm serve
```

Then open [http://127.0.0.1:1511](http://127.0.0.1:1511).

## Canonical Commands

```powershell
pysm --help
pysm serve
pysm status
pysm scripts add --script-path C:\path\to\script.py
pysm scripts start --script-id 1
pysm scripts console --script-id 1
pysm interpreters list
pysm settings change-port --port 1512
```

## Legacy Aliases

The CLI also accepts compatibility aliases from the original requirement set:

- `--add-script`
- `--script-path`
- `--remove-script`
- `--pause`
- `--play`
- `--add-interpreter`
- `--select-interpreter`
- `--list-load`
- `--change-port`
