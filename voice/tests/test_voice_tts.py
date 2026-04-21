"""
test_voice_tts.py — Unit tests for _clean_for_tts() in tts.py.

This function strips Markdown before feeding text to the TTS engine.
A regression here means Charles literally says "asterisk asterisk" or
"hash hash" out loud — instantly user-visible and embarrassing.

_clean_for_tts() is pure (no I/O), so no mocking is needed.
"""

import sys
import os
import pytest
from unittest.mock import MagicMock, patch

# Stub heavy imports that tts.py pulls in at module level
# so tests run without edge-tts, miniaudio, or pyaudio installed.
sys.modules.setdefault("edge_tts", MagicMock())
sys.modules.setdefault("miniaudio", MagicMock())
sys.modules.setdefault("pyaudio", MagicMock())

# audio.py is imported by tts.py — stub the constants it exports
audio_stub = MagicMock()
audio_stub.SAMPLE_RATE = 16000
audio_stub.CHUNK = 512
audio_stub.DEFAULT_SILENCE_THRESHOLD = 500
sys.modules["audio"] = audio_stub

from tts import _clean_for_tts


# ── Code blocks ───────────────────────────────────────────────────────────────

def test_fenced_code_block_replaced_with_label():
    text = "Here's the code:\n```python\nprint('hi')\n```\nDone."
    result = _clean_for_tts(text)
    assert "code block omitted" in result
    assert "print" not in result
    assert "python" not in result


def test_inline_code_strips_backticks():
    result = _clean_for_tts("`rm -rf /`")
    assert "rm -rf /" in result
    assert "`" not in result


# ── Bold / italic ─────────────────────────────────────────────────────────────

def test_double_asterisk_bold_stripped():
    result = _clean_for_tts("**bold text**")
    assert result == "bold text"


def test_single_asterisk_italic_stripped():
    result = _clean_for_tts("*italic*")
    assert result == "italic"


def test_double_underscore_bold_stripped():
    result = _clean_for_tts("__also bold__")
    assert result == "also bold"


# ── Headings ──────────────────────────────────────────────────────────────────

def test_heading_hashes_removed():
    result = _clean_for_tts("## Section Title")
    assert "#" not in result
    assert "Section Title" in result


def test_h1_heading():
    result = _clean_for_tts("# Top Level")
    assert "#" not in result
    assert "Top Level" in result


# ── Links ─────────────────────────────────────────────────────────────────────

def test_markdown_link_becomes_link_text():
    result = _clean_for_tts("[click here](https://example.com)")
    assert "click here" in result
    assert "https://example.com" not in result
    assert "[" not in result


# ── Lists ─────────────────────────────────────────────────────────────────────

def test_bullet_list_strips_dash():
    result = _clean_for_tts("- item one\n- item two")
    assert "item one" in result
    assert "item two" in result
    # The leading "- " should be stripped
    assert result.strip()[:2] != "- "


def test_numbered_list_strips_prefix():
    result = _clean_for_tts("1. First\n2. Second")
    assert "First" in result
    assert "Second" in result
    assert "1." not in result


# ── Horizontal rules ──────────────────────────────────────────────────────────

def test_horizontal_rule_not_literal():
    result = _clean_for_tts("---")
    assert result != "---"


# ── Whitespace normalisation ──────────────────────────────────────────────────

def test_double_newlines_become_space():
    result = _clean_for_tts("line one\n\nline two")
    assert "line one" in result
    assert "line two" in result
    assert "\n" not in result


def test_multiple_spaces_collapsed():
    result = _clean_for_tts("too  many   spaces")
    assert "too many spaces" in result


def test_empty_string_returns_empty():
    assert _clean_for_tts("") == ""


def test_whitespace_only_returns_empty():
    assert _clean_for_tts("   \n  ") == ""


# ── Combined real-world LLM output ───────────────────────────────────────────

def test_combined_llm_output_no_markdown_artifacts():
    llm_output = (
        "## Key Points\n\n"
        "- **Use `pip install`** to install packages\n"
        "- Always check [the docs](https://docs.python.org)\n\n"
        "```bash\npip install requests\n```\n\n"
        "That's it!"
    )
    result = _clean_for_tts(llm_output)

    # No Markdown artifacts
    assert "##" not in result
    assert "**" not in result
    assert "`" not in result
    assert "[" not in result
    assert "```" not in result
    assert "\n" not in result

    # Meaningful content preserved
    assert "pip install" in result
    assert "the docs" in result
    assert "That's it" in result
