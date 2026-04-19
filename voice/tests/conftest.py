"""
conftest.py — Voice test configuration.

Adds the voice/ directory to sys.path so tests can import voice modules
(stt, tts, api_client, etc.) directly by name without installing them as a package.
"""

import sys
import os

# Insert the voice/ directory at the front of sys.path
voice_dir = os.path.join(os.path.dirname(__file__), "..")
if voice_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(voice_dir))
