# Qwythos-9B-Claude-Mythos-5-1M-MTP + llama-server for VS Code on AMD RX 9060 XT

## Hardware Profile

- GPU: AMD Radeon RX 9060 XT (RDNA 4, gfx1200, 32 CU, 16 GB VRAM, 170 W TDP)
- CPU: AMD Ryzen 5 9600X (Zen 5, 6C/12T, 5486 MHz boost)
- RAM: 32 GB DDR5
- ROCm: 7.2 (HIP 7.2.53211, AMD clang 22.0.0)
- OS: CachyOS (Arch-based), kernel 7.1.1-2-cachyos
- iGPU: gfx1036 (Ryzen integrated, 512 MB - not used for inference)

## Available Quantizations

| File                                                | Approx Size | Notes                                  |
|-----------------------------------------------------|-------------|----------------------------------------|
| `Qwythos-9B-Claude-Mythos-5-1M-MTP-Q8_0.gguf`      | ~9.4 GiB    | Highest quality, fits well in 16 GB VRAM |
| `Qwythos-9B-Claude-Mythos-5-1M-MTP-Q6_K.gguf`      | ~7.3 GiB    | Good quality, more headroom for context  |

With 16 GB VRAM both quants fit comfortably. Q8_0 is recommended for best quality.

## Benchmark Results (RX 9060 XT)

Measured with `llama-bench -ngl 99 -fa on`:

| Model                                          | Size      | Prompt (pp512) | Generation (tg128) |
|------------------------------------------------|-----------|----------------|---------------------|
| **Qwythos-9B ... Q8_0**                        | ~9.4 GiB  | TBD            | TBD                 |
| **Qwythos-9B ... Q6_K**                        | ~7.3 GiB  | TBD            | TBD                 |

### Run benchmarks

```bash
HIP_VISIBLE_DEVICES=0 ./build/bin/llama-bench \
    -hf empero-ai/Qwythos-9B-Claude-Mythos-5-1M-GGUF::Q8_0 \
    -hf empero-ai/Qwythos-9B-Claude-Mythos-5-1M-GGUF::Q6_K \
    -ngl 99 \
    -fa on \
    -r 1
```

## Build Configuration (Verified)

```
CMAKE_BUILD_TYPE  = Release
GGML_HIP          = ON
GPU_TARGETS       = gfx1200
GGML_NATIVE       = ON
GGML_HIP_GRAPHS   = ON
GGML_HIP_MMQ_MFMA = ON
GGML_HIP_NO_VMM   = ON
```

If rebuilding from scratch:

```bash
cmake -B build -S . \
    -DCMAKE_BUILD_TYPE=Release \
    -DGGML_HIP=ON \
    -DGPU_TARGETS="gfx1200" \
    -DGGML_NATIVE=ON \
    -DGGML_HIP_GRAPHS=ON \
    -DGGML_HIP_MMQ_MFMA=ON \
    -DGGML_HIP_NO_VMM=ON

cmake --build build --config Release -j$(nproc)
```

## 1. Start llama-server

**Q8_0 (recommended):**

```bash
HIP_VISIBLE_DEVICES=0 ./build/bin/llama-server \
    -hf empero-ai/Qwythos-9B-Claude-Mythos-5-1M-GGUF::Q8_0 \
    -ngl 99 \
    -fa on \
    -c 32768 \
    --host 127.0.0.1 \
    --port 8012
```

**Q6_K (more context headroom):**

```bash
HIP_VISIBLE_DEVICES=0 ./build/bin/llama-server \
    -hf empero-ai/Qwythos-9B-Claude-Mythos-5-1M-GGUF::Q8_0 \
    -ngl 99 \
    -fa on \
    -c 32768 \
    --host 127.0.0.1 \
    --port 8012
```

Verify it is running:

```bash
curl http://127.0.0.1:8012/health
```

The server exposes:
- Chat completions: `http://127.0.0.1:8012/v1/chat/completions`
- Completions: `http://127.0.0.1:8012/v1/completions`
- Infill (FIM): `http://127.0.0.1:8012/infill`
- Models list: `http://127.0.0.1:8012/v1/models`

## 2. Install llama-vscode Extension

1. Open VS Code
2. Go to Extensions (Ctrl+Shift+X)
3. Search for `llama-vscode`
4. Install the extension by ggml-org

## 3. Configure llama-vscode

Open VS Code settings (Ctrl+,) and search for `llama`, or edit `settings.json` directly:

```json
{
    "llama.endpoint": "http://127.0.0.1:8012",
    "llama.api_key": "",
    "llama.fim.enabled": true,
    "llama.chat.enabled": true
}
```

Or configure via the llama-vscode status bar menu:
1. Click "llama-vscode" in the bottom status bar
2. Select the endpoint (http://127.0.0.1:8012)
3. Enable completion and chat features

## 4. Usage

### Code Completion (FIM)
Just start typing in any file. llama-vscode sends fill-in-the-middle requests to the server. Accept suggestions with Tab.

### Chat
Use the llama-vscode chat panel (Ctrl+Shift+M or click status bar) to ask questions about your code, get explanations, or request changes.

## 5. Run as a systemd User Service (Optional)

Create a service so llama-server starts automatically. Swap in Q6_K if you want
more VRAM headroom for longer contexts.

```bash
mkdir -p ~/.config/systemd/user

cat > ~/.config/systemd/user/llama-server.service << 'EOF'
[Unit]
Description=llama.cpp server (Qwythos-9B Q8_0)
After=default.target

[Service]
Type=simple
Environment=HIP_VISIBLE_DEVICES=0
ExecStart=%h/Projects/llama_cpp/build/bin/llama-server \
    -hf empero-ai/Qwythos-9B-Claude-Mythos-5-1M-GGUF::Q8_0 \
    -ngl 99 \
    -fa on \
    -c 32768 \
    --host 127.0.0.1 \
    --port 8012
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable llama-server
systemctl --user start llama-server

# Check status
systemctl --user status llama-server

# View logs
journalctl --user -u llama-server -f
```

## 6. Thinking Mode

If the model supports extended reasoning, consult the model card for the correct
trigger token or system prompt syntax:

```bash
curl http://127.0.0.1:8012/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "system", "content": "You are a helpful coding assistant."},
      {"role": "user", "content": "Write a binary search in Rust."}
    ],
    "temperature": 0.7,
    "top_p": 0.9
  }'
```

## Context Length vs VRAM Budget

With flash attention enabled, KV cache overhead is reduced. 16 GB VRAM gives
good headroom for long contexts with either quant.

**Q8_0 (~9.4 GiB weights):**

| Context Length | Estimated Total VRAM | Status      |
|----------------|----------------------|-------------|
| 8K tokens      | ~10.0 GB             | Comfortable |
| 16K tokens     | ~10.5 GB             | Comfortable |
| 32K tokens     | ~11.5 GB             | Good        |
| 65K tokens     | ~13.5 GB             | OK          |
| 128K tokens    | ~16+ GB              | At limit    |

**Q6_K (~7.3 GiB weights):**

| Context Length | Estimated Total VRAM | Status      |
|----------------|----------------------|-------------|
| 8K tokens      | ~8.0 GB              | Comfortable |
| 32K tokens     | ~9.5 GB              | Good        |
| 128K tokens    | ~14 GB               | OK          |
| 256K+ tokens   | ~16+ GB              | Monitor     |

The 1M context window in the model name reflects training context, not a
practical VRAM limit. Start with `-c 32768` and increase carefully.

## Runtime Flag Reference

| Flag               | Value       | Purpose                                                |
|--------------------|-------------|--------------------------------------------------------|
| `-ngl 99`          | 99          | Offload all layers to GPU                              |
| `-fa on`           | on          | Flash attention: less VRAM for KV cache, faster        |
| `-c 32768`         | 32768       | 32K context window                                     |
| `--host 127.0.0.1` | 127.0.0.1   | Listen on localhost only                               |
| `--port 8012`      | 8012        | Default port for llama-vscode                          |
| `-m`               | /path/file  | Load a local .gguf model file                          |
