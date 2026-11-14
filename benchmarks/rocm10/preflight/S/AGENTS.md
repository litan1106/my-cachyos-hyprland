# Video Subtitle Processing Pipeline

A three-stage pipeline for generating translated subtitles from video files:

```
Video File  →  [1] extract_audio.py  →  WAV
WAV         →  [2] transcribe.py     →  SRT
SRT         →  [3] translate_srt.py  →  Translated SRT
```

---

## Environment

All scripts run inside the project's `uv` virtual environment (`.venv`).

### AMD ROCm (not NVIDIA CUDA)

This pipeline runs on an **AMD GPU via ROCm** — AMD's compute stack equivalent to NVIDIA CUDA.
libraries like `faster-whisper` / `ctranslate2` target the CUDA API, which ROCm's **HIP** layer transparently emulates, so `device="cuda"` is used in code even though the hardware is AMD.

**GPUs detected by `rocminfo`:**
| Architecture | Card | Role |
|---|---|---|
| `gfx1200` | RX 9060 XT | Discrete GPU — used for inference |
| `gfx1036` | Integrated GPU | Ignored via `HIP_VISIBLE_DEVICES=0` |

**Key environment variables:**
```bash
# gfx1200 is newer than what ROCm officially lists; this override tells ROCm to
# treat it as a supported gfx12 device instead of falling back to CPU.
HSA_OVERRIDE_GFX_VERSION=12.0.0

# Select only the discrete RX 9060 XT (device index 0).
# Without this, ROCm may pick up the integrated GPU (gfx1036) as well.
HIP_VISIBLE_DEVICES=0
```
These are set automatically inside `transcribe.py` and `translate_srt.py`.

**Installed packages (relevant):**
| Package | Version | Purpose |
|---|---|---|
| `ctranslate2` | 4.7.2 | GPU inference engine (ROCm 7.2 build) — **must not use the default PyPI wheel** |
| `faster-whisper` | 1.2.1 | GPU-accelerated Whisper transcription |
| `av` | latest | Audio decoding for faster-whisper (PyAV) |
| `numpy` | 2.4.4 | Numerical dependency of ctranslate2 |
| `srt` | 3.5.3 | SRT file parsing and composition |
| `typer-slim` | 0.21.1 | CLI framework |

### Setup

All dependencies are declared in `pyproject.toml`. Install everything with:

```bash
# Step 1: Install all dependencies from pyproject.toml
uv sync

# Step 2: Force-reinstall ctranslate2 from the ROCm index.
# uv sync resolves ctranslate2 from PyPI (CPU-only build) even with extra-index-url.
# This step overwrites it with the correct ROCm 7.2 GPU build.
uv pip install ctranslate2 --extra-index-url https://download.pytorch.org/whl/rocm7.2 --reinstall
```

> **Note:** `[tool.uv.sources]` index-pinning does **not** work with the PyTorch WHL index — `extra-index-url` is the correct mechanism.

---

## Stage 1 — Extract Audio (`extract_audio.py`)

Extracts audio from video files using **FFmpeg**, producing WAV files optimised for Whisper (16 kHz, mono, 16-bit PCM).

### Usage
```bash
uv run extract_audio.py -s <source_dir> [-d <dest_dir>] [-f <glob>]
```

### Arguments
| Flag | Default | Description |
|---|---|---|
| `-s` / `--source_path` | *(required)* | Directory containing video files |
| `-d` / `--destination_path` | same as source | Output directory for WAV files |
| `-f` / `--filter` | `*.mp4` | Glob pattern for input video files |

### Example
```bash
# Extract all MKV files from the Yu/ directory
uv run extract_audio.py -s ./Yu -f "*.mkv"

# Extract MP4s and save WAVs to a separate folder
uv run extract_audio.py -s ./Yu -d ./Yu/audio -f "*.mp4"
```

### FFmpeg settings used
- Sample rate: `16000 Hz`
- Channels: `1` (mono)
- Codec: `pcm_s16le` (16-bit PCM WAV)

### Prerequisites
```bash
sudo apt install ffmpeg
```

---

## Stage 2 — Transcribe (`transcribe.py`)

Transcribes WAV (or other audio/video) files to SRT using **faster-whisper** on AMD GPU via ROCm.

### Usage
```bash
uv run transcribe.py -i <input_path> [-m <model>] [-l <lang>] [-o <output_dir>] [-bs <beam_size>]
```

### Arguments
| Flag | Default | Description |
|---|---|---|
| `-i` / `--input_path` | *(required)* | Single file or directory to transcribe |
| `-m` / `--model_name` | `large-v3` | faster-whisper model name |
| `-l` / `--language` | `ja` | BCP-47 language code of source audio |
| `-o` / `--output_directory` | same as input | Directory to save `.srt` files |
| `-bs` / `--beam_size` | `5` | Beam search width (higher = more accurate, slower) |

### Supported input formats
`.wav`, `.mp4`, `.mkv`, `.mp3`, `.m4a`, `.mov`

### Example
```bash
# Transcribe all WAV files in Yu/ (Japanese audio)
uv run transcribe.py -i ./Yu -l ja

# Transcribe a single file with a smaller/faster model
uv run transcribe.py -i ./Yu/episode01.wav -m medium -l ja -o ./Yu/subs
```

### Model / device settings
| Setting | Value | Notes |
|---|---|---|
| `device` | `cuda` | ROCm's HIP layer emulates the CUDA API — use `"cuda"` even on AMD |
| `compute_type` | `float16` | Optimal for RDNA4 / gfx1200 (RX 9060 XT) |

### Installing faster-whisper

> **Warning:** Installing `ctranslate2` from the default PyPI index installs a CPU-only build.
> faster-whisper will silently fall back to CPU, running orders of magnitude slower.
> Always install `ctranslate2` from the ROCm index **first**.

```bash
# 1. Install ctranslate2 from the ROCm index (check your version: apt list --installed | grep rocm-core)
uv pip install ctranslate2 --extra-index-url https://download.pytorch.org/whl/rocm7.2

# 2. Install faster-whisper without deps (ctranslate2 is already installed above)
uv pip install --no-deps faster-whisper

# 3. Install av (PyAV) — audio decoding dep, also skipped by --no-deps
uv pip install av
```

Confirmed working versions on ROCm 7.2:
- `ctranslate2==4.7.2` (from `https://download.pytorch.org/whl/rocm7.2`)
- `faster-whisper==1.2.1`

---

## Stage 3 — Translate SRT (`translate_srt.py`)

Translates `.srt` files to any language using a local **llama.cpp** GGUF model (via `llama-cli`). Processes subtitles in configurable chunks to fit the model's context window.

### Usage
```bash
uv run translate_srt.py -i <input_path> [-o <output_dir>] [-sl <source_lang>] [-tl <target_lang>] \
    [-m <model_path>] [-c <llama_cli_path>] [--chunk-size <n>]
```

### Arguments
| Flag | Default | Description |
|---|---|---|
| `-i` / `--input_path` | *(required)* | Single `.srt` file or directory of `.srt` files |
| `-o` / `--output_directory` | same as input | Directory to save translated SRT files |
| `-sl` / `--source_lang` | `Japanese` | Source language name (used in the prompt) |
| `-tl` / `--target_lang` | `Simplified Chinese` | Target language name (used in the prompt) |
| `-m` / `--model` | `~/.cache/llama.cpp/Qwen2.5-14B-Q4_K_M.gguf` | Path to GGUF model file |
| `-c` / `--llama_cli_path` | `~/llama_cpp/build/bin/llama-cli` | Path to `llama-cli` binary |
| `--chunk-size` | `50` | Subtitle entries per translation batch |

### Example
```bash
# Translate Japanese SRT to Simplified Chinese (default)
uv run translate_srt.py -i ./Yu/episode01.srt

# Translate to English
uv run translate_srt.py -i ./Yu -sl Japanese -tl English -o ./Yu/en_subs

# Use a custom model and llama-cli
uv run translate_srt.py -i ./Yu/episode01.srt \
    -m ~/.cache/llama.cpp/my-model.gguf \
    -c ~/llama_cpp/build/bin/llama-cli
```

### Output filename convention
Input `episode01.srt` → output `episode01.zh.srt`  
(The `.zh.` infix is currently hardcoded; adjust the script for other target languages.)

### llama-cli GPU settings used
| Flag | Value | Notes |
|---|---|---|
| `-ngl` | `35` | GPU layers offloaded (out of 40 for Qwen2.5-14B) |
| `-fa on` | on | Flash Attention (reduces VRAM) |
| `-c` | `16384` | Context window size |
| `-ctk` / `-ctv` | `q8_0` | KV-cache quantisation (saves ~50% VRAM) |

---

## Full Pipeline Example

```bash
# 1. Extract audio from all MKV files in ./Yu
uv run extract_audio.py -s ./Yu -f "*.mkv"

# 2. Transcribe all WAVs to Japanese SRT
uv run transcribe.py -i ./Yu -l ja

# 3. Translate SRTs from Japanese → English
uv run translate_srt.py -i ./Yu -sl Japanese -tl English
```

---

## Troubleshooting

### ROCm / GPU not detected
```bash
# Check which GPU architectures ROCm sees
rocminfo | grep gfx
# Expected output includes gfx1200 (RX 9060 XT) and gfx1036 (integrated GPU)

# gfx1200 is not yet in ROCm's official support list — override so it is treated
# as a supported gfx12 device:
export HSA_OVERRIDE_GFX_VERSION=12.0.0

# Restrict ROCm to the discrete card only (avoids integrated GPU interference):
export HIP_VISIBLE_DEVICES=0
```

### faster-whisper falls back to CPU
- Ensure `ctranslate2` is the ROCm build, not the default CPU/CUDA wheel.
- Verify with `uv pip list | grep ctranslate2`.
- Ensure `HSA_OVERRIDE_GFX_VERSION=12.0.0` is set before running — without it, ROCm may not recognise the gfx1200 device and silently fall back to CPU.

### llama-cli not found
- Build llama.cpp from source with ROCm support or update `--llama_cli_path`.
- Default path: `~/llama_cpp/build/bin/llama-cli`

### SRT parse errors from translate_srt.py
- Reduce `--chunk-size` (e.g., `--chunk-size 20`) so the model output stays within context.
- The script prints raw model output for failed chunks to help debug malformed responses.
