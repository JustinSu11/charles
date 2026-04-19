"""
test_voice_stt.py — Unit tests for the silence guard and hallucination filter in stt.py.

The hallucination filter discards Whisper output if >30% of characters are non-ASCII.
This is a safety-critical guard: a regression would cause Charles to speak
multilingual garbage back at the user on near-silence inputs.

Whisper itself is never loaded — _load_model is mocked so tests run without
the 140 MB model download and heavy torch import.
"""

import sys
import pytest
import numpy as np
from unittest.mock import MagicMock, patch

# Stub whisper before stt.py is imported so the heavy import is never triggered
whisper_stub = MagicMock()
sys.modules.setdefault("whisper", whisper_stub)

import stt


def _make_audio(n_samples: int) -> np.ndarray:
    """Create a silent float32 audio array of the given length."""
    return np.zeros(n_samples, dtype=np.float32)


def _mock_model(return_text: str) -> MagicMock:
    """Return a mock Whisper model that transcribes to return_text."""
    model = MagicMock()
    model.transcribe.return_value = {"text": return_text}
    return model


# ── Silence / short audio guard ───────────────────────────────────────────────

def test_none_audio_returns_empty():
    assert stt.transcribe(None) == ""


def test_too_short_audio_returns_empty():
    # 1599 samples < 1600 threshold
    audio = _make_audio(1599)
    assert stt.transcribe(audio) == ""


def test_exactly_threshold_audio_proceeds():
    # 1600 samples == boundary — transcription should run
    audio = _make_audio(1600)
    with patch.object(stt, "_load_model", return_value=_mock_model("hello")):
        result = stt.transcribe(audio)
    assert result == "hello"


# ── Hallucination filter ──────────────────────────────────────────────────────

def test_ascii_only_text_returned_as_is():
    audio = _make_audio(16000)
    with patch.object(stt, "_load_model", return_value=_mock_model("Hello, how can I help?")):
        result = stt.transcribe(audio)
    assert result == "Hello, how can I help?"


def test_exactly_30_percent_non_ascii_returned():
    # Threshold is > 0.30, so exactly 30% should NOT be discarded
    # 7 ASCII + 3 non-ASCII = 10 chars → exactly 30%
    text = "aaaaaaa" + "é" * 3   # 7 ASCII, 3 non-ASCII (é is >127)
    assert len(text) == 10
    non_ascii_ratio = sum(1 for c in text if ord(c) > 127) / len(text)
    assert non_ascii_ratio == 0.30

    audio = _make_audio(16000)
    with patch.object(stt, "_load_model", return_value=_mock_model(text)):
        result = stt.transcribe(audio)
    assert result == text  # not discarded


def test_31_percent_non_ascii_discarded():
    # 69 ASCII + 31 non-ASCII = 100 chars → 31% → discarded
    text = "a" * 69 + "é" * 31
    assert len(text) == 100
    non_ascii_ratio = sum(1 for c in text if ord(c) > 127) / len(text)
    assert non_ascii_ratio > 0.30

    audio = _make_audio(16000)
    with patch.object(stt, "_load_model", return_value=_mock_model(text)):
        result = stt.transcribe(audio)
    assert result == ""


def test_all_non_ascii_discarded():
    garbage = "αβγδεζηθ" * 20   # 100% non-ASCII
    audio = _make_audio(16000)
    with patch.object(stt, "_load_model", return_value=_mock_model(garbage)):
        result = stt.transcribe(audio)
    assert result == ""


# ── Return value stripping ────────────────────────────────────────────────────

def test_whitespace_stripped_from_result():
    audio = _make_audio(16000)
    with patch.object(stt, "_load_model", return_value=_mock_model("  hello  ")):
        result = stt.transcribe(audio)
    assert result == "hello"


def test_empty_model_output_returns_empty():
    audio = _make_audio(16000)
    with patch.object(stt, "_load_model", return_value=_mock_model("")):
        result = stt.transcribe(audio)
    assert result == ""
