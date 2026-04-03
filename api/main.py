"""Entry point for the Charles API. Run with: python main.py"""
import os
import sys

# Ensure the api/ directory is on sys.path so the `app` package is importable
# regardless of which directory the process was launched from.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000)
