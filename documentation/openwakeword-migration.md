# Migration Plan: Picovoice Porcupine → OpenWakeWord

**Status:** Proposed  
**Author:** mokumoose93  
**Date:** 2026-04-05  
**Goal:** Remove the Picovoice API key requirement by replacing `pvporcupine` with the fully open-source `openwakeword` library.

---

## 1. Motivation

Picovoice Porcupine currently requires users to:

1. Create an account at `console.picovoice.ai`
2. Generate a personal access key
3. Generate platform-specific `.ppn` model files for each wake phrase
4. Enter the key during the first-run setup wizard

This is a significant friction point. OpenWakeWord is a fully open-source, Apache-2.0-licensed wake word engine that runs entirely locally with no account, API key, or proprietary model files required.

---

## 2. What Is OpenWakeWord?

[OpenWakeWord](https://github.com/dscripka/openWakeWord) is a Python library that uses ONNX or TFLite models for always-on, CPU-efficient wake word detection. Key properties:

- **No API key or account** — fully local, no licensing restrictions
- **Pre-trained models available** — community and official models (`.onnx` format)
- **Custom model training** — training pipeline available for custom phrases like "Hey Charles"
- **Audio format** — 16 kHz mono 16-bit PCM (same as Porcupine)
- **Frame size** — 1280 samples (80 ms at 16 kHz), compared to Porcupine's 512-sample frames
- **Scoring** — returns a `float` score per model (0.0–1.0) rather than a keyword index

---

## 3. Scope of Changes

| File | Change Required |
|---|---|
| `voice/wake_word.py` | Full rewrite of detection logic |
| `voice/requirements.txt` | Replace `pvporcupine` with `openwakeword` |
| `voice/models/` | Replace `.ppn` files with `.onnx` model(s) |
| `launcher/wizard.js` | Remove Picovoice key validation step |
| `.env` / `.env.example` | Remove `PICOVOICE_ACCESS_KEY` |
| `voice/README.md` | Update setup instructions |

`voice/main.py`, `voice/audio.py`, `voice/stt.py`, and `voice/tts.py` require **no changes** — the wake word module's public API (`run_forever`, `wait_for_wake_word`) will be preserved.

---

## 4. Audio Frame Size Adjustment

This is the only non-trivial integration concern.

- **Current (`audio.py`):** `CHUNK = 512` — the MicrophoneStream reads 512-sample frames, sized to match Porcupine's `frame_length`.
- **OpenWakeWord:** requires 1280-sample frames (80 ms at 16 kHz).

**Solution:** Accumulate frames in `wake_word.py` before passing to the model rather than changing `CHUNK` globally (other consumers like silence detection use the existing chunk size):

```python
_OWW_FRAME_SAMPLES = 1280
_buffer = []

pcm_bytes = mic.read_frame()  # 512 samples
_buffer.extend(pcm_int16_list)
if len(_buffer) >= _OWW_FRAME_SAMPLES:
    frame = _buffer[:_OWW_FRAME_SAMPLES]
    _buffer = _buffer[_OWW_FRAME_SAMPLES:]
    prediction = oww_model.predict(np.array(frame, dtype=np.int16))
    # check scores ...
```

This keeps `CHUNK` and the rest of the audio pipeline unchanged.

---

## 5. Wake Word Models

### 5a. Development / Testing (Immediate)

Use a pre-built OpenWakeWord model to validate the integration before training a custom "Hey Charles" model. Recommended options:

| Model | Trigger Phrase | Download |
|---|---|---|
| `hey_jarvis` | "Hey Jarvis" | Built-in to openwakeword |
| `alexa` | "Alexa" | Built-in to openwakeword |
| `hey_mycroft` | "Hey Mycroft" | Built-in to openwakeword |

These can be loaded by name without any file:

```python
from openwakeword.model import Model
model = Model(wakeword_models=["hey_jarvis"])
```

### 5b. Production ("Hey Charles" custom model)

To restore the "Hey Charles" and "Charles" wake words, a custom model must be trained using the [OpenWakeWord training tools](https://github.com/dscripka/openWakeWord/blob/main/docs/custom_models.md).

**Training requirements:**
- Python environment with `openwakeword[train]` extras
- ~30–100 positive audio samples of the phrase
- The training script generates a `.onnx` file
- Model file is placed in `voice/models/hey-charles.onnx`

**Community models:** Check the [OpenWakeWord community models](https://github.com/dscripka/openWakeWord/blob/main/openwakeword/resources/models/README.md) repository — a "Hey Charles" model may already exist.

**Fallback during transition:** Until a custom model is trained, ship the integration using `hey_jarvis` as the default trigger, clearly documented in the README.

---

## 6. Implementation Steps

### Step 1 — Update `voice/requirements.txt`

Remove:
```
pvporcupine==4.0.0
```

Add:
```
openwakeword>=0.6.0
numpy>=1.21.0       # already likely present; required by openwakeword
```

### Step 2 — Rewrite `voice/wake_word.py`

Replace the entire Porcupine integration. The module's **public interface is preserved** (`wait_for_wake_word`, `run_forever`, same signatures) so `main.py` requires no changes.

Key implementation outline:

```python
"""
wake_word.py — OpenWakeWord multi-model wake word detection.

OpenWakeWord is a fully open-source, Apache-2.0-licensed wake word engine.
No API key or account required.

Models
------
Place any .onnx model files in voice/models/ to use custom wake words.
Built-in models (e.g. "hey_jarvis") are available without model files.
See: https://github.com/dscripka/openWakeWord

Sensitivity
-----------
WAKE_WORD_THRESHOLD in .env sets the detection threshold (0.0–1.0).
Higher values = fewer false positives but may miss some detections.
Default: 0.5
"""

import numpy as np
from openwakeword.model import Model

_OWW_FRAME_SAMPLES = 1280          # 80 ms at 16 kHz
THRESHOLD: float = float(os.getenv("WAKE_WORD_THRESHOLD", "0.5"))

def _discover_models() -> list[Path]:
    """Return all .onnx files in voice/models/, sorted alphabetically."""
    if not _MODELS_DIR.exists():
        return []
    return sorted(_MODELS_DIR.glob("*.onnx"))

def _load_oww_model(onnx_paths: list[Path]) -> Model:
    if onnx_paths:
        return Model(
            wakeword_models=[str(p) for p in onnx_paths],
            inference_framework="onnx",
        )
    # Fallback to a built-in model during development
    logger.warning("No .onnx models found — falling back to built-in 'hey_jarvis' for testing.")
    return Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")

def wait_for_wake_word(on_detected=None, input_device_index=None, stop_event=None) -> str:
    onnx_paths = _discover_models()
    oww = _load_oww_model(onnx_paths)
    model_names = list(oww.models.keys())
    buffer = []

    with MicrophoneStream(input_device_index=input_device_index) as mic:
        while True:
            if stop_event and stop_event.is_set():
                return "stopped"

            pcm_bytes = mic.read_frame()
            samples = list(
                int.from_bytes(pcm_bytes[i:i+2], byteorder="little", signed=True)
                for i in range(0, len(pcm_bytes), 2)
            )
            buffer.extend(samples)

            if len(buffer) >= _OWW_FRAME_SAMPLES:
                frame = np.array(buffer[:_OWW_FRAME_SAMPLES], dtype=np.int16)
                buffer = buffer[_OWW_FRAME_SAMPLES:]
                scores = oww.predict(frame)

                for name, score in scores.items():
                    if score >= THRESHOLD:
                        logger.info("Wake word detected: '%s' (score=%.3f)", name, score)
                        if on_detected:
                            on_detected(name)
                        return name
```

The `run_forever` wrapper in `wake_word.py` requires only minor updates (logging strings — replace `.ppn` with `.onnx` references).

### Step 3 — Update `launcher/wizard.js`

Remove the `wizard:validate-picovoice` IPC handler and the `validatePicovoiceKey()` function entirely (lines 101–104 and 159–236). The step that prompts the user for a Picovoice key during setup should be removed from the wizard flow.

If the wizard has a step list or progress indicator, remove the Picovoice step from that list as well.

### Step 4 — Update `.env.example`

Remove:
```
PICOVOICE_ACCESS_KEY=your_key_here
```

Add (optional sensitivity setting):
```
# Wake word detection threshold (0.0–1.0). Higher = fewer false positives.
# WAKE_WORD_THRESHOLD=0.5
```

### Step 5 — Update `voice/models/`

- Delete `Hey-Charles_en_windows_v4_0_0.ppn` and `charles_en_windows_v4_0_0.ppn`
- Add the trained `hey-charles.onnx` once available (or leave empty to use fallback)
- Update `.gitkeep` / README to reflect the new model format

### Step 6 — Update `voice/README.md`

- Remove the Picovoice console link and `.ppn` generation instructions
- Add instructions for placing `.onnx` model files
- Link to OpenWakeWord custom model training docs
- Update the audio pipeline diagram (replace "pvporcupine" label)

---

## 7. Environment Variable Changes

| Variable | Before | After |
|---|---|---|
| `PICOVOICE_ACCESS_KEY` | Required | **Removed** |
| `WAKE_WORD_SENSITIVITY` | Used | **Renamed** to `WAKE_WORD_THRESHOLD` |
| `WAKE_WORD_SENSITIVITIES` | Per-model list | **Removed** (single threshold applies to all models) |

> **Note on renaming:** `SENSITIVITY` (Porcupine concept) and `THRESHOLD` (OpenWakeWord concept) are semantically identical here. Renaming improves clarity. Both control the same thing — how confidently the model must score before triggering.

---

## 8. Testing Plan

### Unit / Integration

- [ ] `wait_for_wake_word()` returns a model name string on detection
- [ ] `wait_for_wake_word()` respects `stop_event`
- [ ] `run_forever()` re-arms after each detection (existing behaviour preserved)
- [ ] Falls back to `hey_jarvis` when `voice/models/` is empty
- [ ] No `EnvironmentError` raised at startup (previously required for missing key)

### End-to-End Voice Flow

- [ ] Say trigger phrase → Charles responds ("Yes?", "I'm listening.")
- [ ] False positive rate acceptable in normal room conditions
- [ ] Detection latency ≤ 1 s from end of phrase to acknowledgement
- [ ] CPU usage during idle listening ≤ Porcupine baseline

### Platform

- [ ] Windows (WASAPI / default PyAudio device)
- [ ] macOS (CoreAudio)
- [ ] Linux (ALSA / PulseAudio)

---

## 9. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| No pre-trained "Hey Charles" model exists in the community | Medium | Medium | Use `hey_jarvis` as interim; train custom model in parallel |
| OpenWakeWord false positive rate higher than Porcupine | Medium | Low | Raise `WAKE_WORD_THRESHOLD` (0.6–0.7); tune per environment |
| 1280-sample frame accumulation adds latency | Low | Low | 80 ms buffer is imperceptible to users |
| openwakeword ONNX runtime incompatibility on some platforms | Low | Medium | Test on all 3 platforms before release; `onnxruntime` is well-supported |
| Wizard step removal breaks wizard flow state machine | Low | Medium | Review `wizard.js` step array after removing the Picovoice step |

---

## 10. Out of Scope

- Changes to STT (`stt.py`), TTS (`tts.py`), or API client (`api_client.py`)
- Training the "Hey Charles" custom model (separate task)
- Changing the audio chunk size (`CHUNK`) in `audio.py`
- Multi-language wake word support

---

## 11. Definition of Done

- [ ] `pvporcupine` removed from `requirements.txt`
- [ ] `PICOVOICE_ACCESS_KEY` removed from `.env.example` and wizard
- [ ] `wake_word.py` uses OpenWakeWord with preserved public API
- [ ] Wizard first-run setup no longer asks for a Picovoice key
- [ ] End-to-end voice flow works on Windows with at least one model
- [ ] `voice/README.md` updated
- [ ] Existing `.ppn` model files removed from `voice/models/`
