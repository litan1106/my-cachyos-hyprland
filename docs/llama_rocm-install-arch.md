# llama.cpp with ROCm 7.2 on Arch Linux (CachyOS)

[Documentation index](README.md) · [Current ROCm 10 record](rocm-install-arch.md) · [Qwythos workflow](llama_qwythos.md)

Date: June 2026

This is a recorded ROCm 7.2 workflow for building `llama.cpp` with the HIP backend; it does not validate llama-server on ROCm 10. Tested on CachyOS (kernel `7.0.12-1-cachyos`) with an RX 9060 XT (gfx1200 / RDNA4) discrete GPU alongside a Ryzen 9600X integrated GPU. CachyOS is Arch-based so all `pacman` commands apply as-is.

---

For the recorded setup, see the historical ROCm 7.2 [prerequisites](rocm-install-arch.md#prerequisites), [SDK installation](rocm-install-arch.md#1-install-the-rocm-hip-sdk), [GPU groups](rocm-install-arch.md#2-add-your-user-to-the-gpu-groups), [environment](rocm-install-arch.md#3-set-up-environment-variables), and [device check](rocm-install-arch.md#4-verify-rocm-sees-the-gpu). The original llama record listed both GPUs as `gfx1200`; the historical device check instead records the iGPU as `gfx1036`. Verify the device identity and index on the machine in use.

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
