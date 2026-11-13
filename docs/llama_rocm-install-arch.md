## Installing ROCm 7.2 on Arch Linux (CachyOS)

Date: June 2026

This covers installing ROCm 7.2 from the Arch `extra` repository and configuring the environment for building `llama.cpp` with the HIP backend. Tested on CachyOS (kernel `7.0.12-1-cachyos`) with an RX 9060 XT (gfx1200 / RDNA4) discrete GPU alongside a Ryzen 9600X integrated GPU. CachyOS is Arch-based so all `pacman` commands apply as-is.

---

### Prerequisites

- Arch Linux with an up-to-date system
- A supported AMD GPU (RDNA4 / gfx1200, e.g. RX 9060 XT)
- `base-devel` and `cmake` installed

```bash
sudo pacman -Syu
sudo pacman -S --needed base-devel cmake git
```

---

### 1. Install the ROCm HIP SDK

ROCm 7.2 is in the official `extra` repo (current version: 7.2.4-1).

```bash
sudo pacman -S rocm-hip-sdk
```

This pulls in `rocm-llvm`, `rocblas`, `hipblas`, `hipblaslt`, `miopen-hip`, and the HIP runtime as dependencies. Verify the install:

```bash
pacman -Qi rocm-hip-sdk | grep Version
/opt/rocm/bin/hipconfig --version
```

`hipconfig` is not in PATH until step 3; use the full path here.

---

### 2. Add your user to the GPU groups

```bash
sudo usermod -aG render,video $USER
```

Log out and back in (or `newgrp render`) for the group change to take effect.

---

### 3. Set up environment variables

Add to `~/.bashrc`:

```bash
export ROCM_PATH=/opt/rocm
export PATH="$ROCM_PATH/bin:$PATH"
```

Reload the shell or open a new terminal to pick up the changes.

`HSA_OVERRIDE_GFX_VERSION` is not needed on this hardware -- ROCm 7.2 correctly identifies the RX 9060 XT as `gfx1200` without it.

---

### 4. Verify ROCm sees the GPU

```bash
rocminfo | grep -E 'Name|gfx'
```

Expected output (abridged):

```
Name:           gfx1200
Marketing Name: AMD Radeon RX 9060 XT
Vendor Name:    AMD
Name:           gfx1200
Marketing Name: AMD Ryzen 5 9600X 6-Core Processor
Vendor Name:    AMD
```

Both the discrete RX 9060 XT and the Ryzen 9600X iGPU appear as `gfx1200` -- the Ryzen 9000 series uses RDNA4 for its integrated GPU as well. Use `rocm-smi --showid` to find which device index maps to the discrete card.

---

### 5. Build llama.cpp with HIP

For the RX 9060 XT the target is `gfx1200`. With a dual-GPU system, pin the build to the discrete card:

```bash
export HIP_PATH=$(hipconfig -R)
export HIPCXX=$(hipconfig -l)/clang

cmake -S . -B build \
  -DGGML_HIP=ON \
  -DGPU_TARGETS=gfx1200 \
  -DGGML_HIP_ROCWMMA_FATTN=OFF \
  -DCMAKE_BUILD_TYPE=Release

cmake --build build --config Release -- -j$(nproc)
```

Binaries land in `build/bin/` (e.g. `llama-cli`, `llama-server`).

**Dual-GPU note:** when running, set `HIP_VISIBLE_DEVICES` to the index of the discrete card (usually `0`) so llama.cpp does not try to use both:

```bash
HIP_VISIBLE_DEVICES=0 ./build/bin/llama-cli ...
```

Or export it permanently in your shell config.

---

### 6. Runtime notes

- **Select discrete GPU:** `HIP_VISIBLE_DEVICES=0` (discrete is usually index 0; verify with `rocm-smi`)
- **Use iGPU unified memory:** `GGML_CUDA_ENABLE_UNIFIED_MEMORY=1 HIP_VISIBLE_DEVICES=1`
- **Force GFX detection:** `HSA_OVERRIDE_GFX_VERSION=12.0.0`

---

### Troubleshooting

| Symptom | Fix |
|---|---|
| `hipcc: command not found` | Ensure `$ROCM_PATH/bin` is in `PATH`; reinstall `rocm-hip-sdk` |
| `error: HSA_STATUS_ERROR_INVALID_ISA` | Set `HSA_OVERRIDE_GFX_VERSION` to match your GPU |
| `hipblaslt` link errors | Confirm `rocm-hip-sdk` 7.2+ is installed; it includes `hipblaslt` |
| Permission denied on `/dev/kfd` or `/dev/dri` | Confirm `render` and `video` group membership, then re-login |
| ROCm sees wrong GPU count | Use `HIP_VISIBLE_DEVICES` to select the correct device index |

---

### 7. Verify the build

**Check the binary exists:**

```bash
ls build/bin/llama-cli
```

**List detected devices:**

```bash
HIP_VISIBLE_DEVICES=0 ./build/bin/llama-cli --list-devices
```

Expected output:

```
Available devices:
  ROCm0: AMD Radeon RX 9060 XT (16304 MiB, 16218 MiB free)
```

**Smoke test with a model:**

```bash
HIP_VISIBLE_DEVICES=0 ./build/bin/llama-cli \
  -m /path/to/model.gguf \
  -p "Hello" \
  -n 16 \
  --gpu-layers 99 \
  --log-disable
```

Look for `ggml_hip: using device 0 (AMD Radeon RX 9060 XT)` in the output confirming inference runs on the discrete GPU.

**Monitor GPU load** (separate terminal):

```bash
watch -n 1 rocm-smi
```

GPU utilization should spike during inference.
