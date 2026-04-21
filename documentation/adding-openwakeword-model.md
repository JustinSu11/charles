# Adding an OpenWakeWord Model to Charles

Charles uses [OpenWakeWord](https://github.com/dscripka/openWakeWord) for always-on wake word detection. It runs entirely on-device — no API key or internet connection required for wake word detection.

---

## How model loading works

On startup, `voice/wake_word.py` scans `voice/models/` for any `.onnx` files and loads them all simultaneously. If no `.onnx` files are found, it falls back to the built-in `hey_jarvis` model so the service always starts.

```
voice/models/
├── hey-charles.onnx    ← loaded automatically if present
└── charles.onnx        ← multiple models can coexist
```

Any model that scores above `WAKE_WORD_THRESHOLD` (default `0.5`) triggers detection.

---

## Option 1 — Use a pre-built community model

The OpenWakeWord project maintains a library of pre-trained models for common phrases. These are ready to use without training.

**Available built-in models** (usable by name, no file needed):

| Model name   | Trigger phrase |
| ------------ | -------------- |
| `hey_jarvis` | "Hey Jarvis"   |
| `alexa`      | "Alexa"        |
| `hey_mycroft`| "Hey Mycroft"  |

The default fallback is `hey_jarvis`. To use a different built-in model without adding a file, edit [voice/wake_word.py](../voice/wake_word.py) and change the fallback model name in `_load_oww_model()`.

**Community `.onnx` models** — check the [OpenWakeWord community models page](https://github.com/dscripka/openWakeWord/blob/main/openwakeword/resources/models/README.md) for downloadable `.onnx` files contributed by users.

To use one:
1. Download the `.onnx` file
2. Place it in `voice/models/`
3. Restart the voice service — it will be picked up automatically

---

## Option 2 — Train a custom "Hey Charles" model

To use your own wake phrase (e.g. "Hey Charles"), you need to train a custom model using OpenWakeWord's training pipeline.

### Prerequisites

- Python 3.10–3.12
- ~30–100 positive audio samples of your wake phrase (`.wav` files, 16 kHz mono)
- The `openwakeword[train]` extras installed:

```bash
pip install "openwakeword[train]"
```

### Training steps

1. **Collect positive samples** — record yourself (or use TTS) saying "Hey Charles" 30–100 times. Save as 16 kHz mono `.wav` files.

2. **Follow the official training guide** at:
   [https://github.com/dscripka/openWakeWord/blob/main/docs/custom_models.md](https://github.com/dscripka/openWakeWord/blob/main/docs/custom_models.md)

3. **Export the model** — the training script produces a `.onnx` file.

4. **Place the model in `voice/models/`**:

   ```
   voice/models/hey-charles.onnx
   ```

5. **Restart the voice service** — it will be detected and loaded automatically.

---

## Verifying a model loaded

When the voice service starts, it logs which models are active:

```
Wake word loop started — listening for: hey-charles | charles
```

If no `.onnx` files are present, you will see:

```
No .onnx models found in voice/models/ — falling back to built-in 'hey_jarvis' for testing.
```

---

## Tuning the detection threshold

If Charles triggers too often (false positives) or not often enough, adjust `WAKE_WORD_THRESHOLD` in your `.env` file:

```
# Default: 0.5
WAKE_WORD_THRESHOLD=0.6
```

| Value | Effect |
| ----- | ------ |
| `0.3` | More sensitive — catches quiet or mumbled phrases, more false positives |
| `0.5` | Default — balanced for typical indoor environments |
| `0.7` | Less sensitive — fewer false positives, may miss quiet speech |

---

## Removing a model

To stop Charles from responding to a particular phrase, delete the corresponding `.onnx` file from `voice/models/` and restart the voice service.
