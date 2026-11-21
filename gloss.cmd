@echo off
rem Gloss launcher. The virtualenv lives outside OneDrive so its ~1 GB of files are not synced.
set "UV_PROJECT_ENVIRONMENT=%LOCALAPPDATA%\Gloss\venv"
cd /d "%~dp0"
uv run --python 3.12 pythonw -m gloss
