"""Development helper: start uvicorn with auto-reload."""
import subprocess
import sys
import os

os.chdir(os.path.join(os.path.dirname(__file__), ".."))
subprocess.run([
    sys.executable, "-m", "uvicorn",
    "backend.app.main:app",
    "--reload",
    "--port", "8000",
])
