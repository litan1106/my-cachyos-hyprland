#!/usr/bin/env bash
# fix-comfyui-rocm.sh
# Fixes the ComfyUI AUR post-install for AMD ROCm GPUs.
# Tested: RX 9060 XT (gfx1200 / RDNA4), ROCm 7.2, CachyOS (Arch).
# Must be run with sudo.
#
# Usage:
#   sudo bash fix-comfyui-rocm.sh
#
# Override GPU target if auto-detection fails (not normally needed on ROCm 7.2):
#   GFX_OVERRIDE=gfx1200 sudo bash fix-comfyui-rocm.sh
#
# Override discrete GPU device index (default: 0):
#   HIP_DEVICE=1 sudo bash fix-comfyui-rocm.sh

# ── ROCm path (matches rocm-install-arch.md) ─────────────────────────────────
export ROCM_PATH=/opt/rocm
export PATH="${ROCM_PATH}/bin:${PATH}"

set -euo pipefail

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
ok()      { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
die()     { echo -e "${RED}[ERROR]${RESET} $*" >&2; exit 1; }
section() { echo -e "\n${BOLD}══ $* ══${RESET}"; }

# ── Config ────────────────────────────────────────────────────────────────────
COMFY_USER="comfy"
COMFY_HOME="/opt/comfyui"
VENV="${COMFY_HOME}/venv"
PIP_CACHE="${COMFY_HOME}/.pip-cache"
ROCM_INDEX="https://download.pytorch.org/whl/rocm7.2"
SERVICE_OVERRIDE="/etc/systemd/system/comfyui.service.d/rocm.conf"

# Discrete GPU device index. The Ryzen 9600X iGPU also appears as gfx1200
# alongside the RX 9060 XT — use HIP_VISIBLE_DEVICES=0 to pin the discrete card.
# (See rocm-install-arch.md §5 "Dual-GPU note")
HIP_DEVICE="${HIP_DEVICE:-0}"

# ── Sanity checks ─────────────────────────────────────────────────────────────
[[ $EUID -ne 0 ]] && die "Run this script with sudo: sudo bash $0"

ROCMINFO="${ROCM_PATH}/bin/rocminfo"
[[ -x "$ROCMINFO" ]] || die "rocminfo not found at ${ROCMINFO}. Is rocm-hip-sdk installed? (sudo pacman -S rocm-hip-sdk)"

# ── GPU detection ─────────────────────────────────────────────────────────────
section "Detecting GPU"

# rocm-install-arch.md §3: HSA_OVERRIDE_GFX_VERSION is NOT needed on ROCm 7.2
# with gfx1200 — it is correctly identified natively.

# Allow manual override for edge cases
GFX="${GFX_OVERRIDE:-}"

# Method 1: rocminfo as the comfy user (/dev/kfd access via render group)
if [[ -z "$GFX" ]]; then
    GFX=$(sudo -u "${COMFY_USER}" "$ROCMINFO" 2>/dev/null \
          | awk '/Name:.*gfx/{print $2; exit}' || true)
    [[ -n "$GFX" ]] && info "GPU detected via rocminfo (comfy user)"
fi

# Method 2: rocminfo as root (works if root is in the render group)
if [[ -z "$GFX" ]]; then
    GFX=$("$ROCMINFO" 2>/dev/null | awk '/Name:.*gfx/{print $2; exit}' || true)
    [[ -n "$GFX" ]] && info "GPU detected via rocminfo (root)"
fi

# Method 3: lspci device-ID table (no /dev/kfd access needed)
# (rocm-install-arch.md §4: rocm-smi --showid to identify device index)
if [[ -z "$GFX" ]]; then
    if command -v lspci &>/dev/null; then
        PCI_ID=$(lspci -nn 2>/dev/null \
                 | grep -i 'VGA\|Display\|3D' \
                 | grep -i AMD \
                 | grep -oi '\[1002:[0-9a-f]*\]' \
                 | head -1 | tr -d '[]')
        case "$PCI_ID" in
            # Navi 44 — RX 9060 / 9060 XT → gfx1200
            1002:7480|1002:7481|1002:7482|1002:7483|1002:7484) GFX="gfx1200" ;;
            # Navi 48 — RX 9070 / 9070 XT → gfx1201
            1002:7460|1002:7461|1002:7462|1002:7463)           GFX="gfx1201" ;;
        esac
        [[ -n "$GFX" ]] && info "GPU detected via lspci (PCI ID: ${PCI_ID})"
    fi
fi

# Give up — ask for a manual override
if [[ -z "$GFX" ]]; then
    echo
    warn "Could not auto-detect GPU target."
    warn "rocminfo needs /dev/kfd access (render group membership)."
    warn "Fix and re-run:"
    warn "  sudo usermod -aG render,video ${COMFY_USER} && newgrp render"
    warn "Or override the GPU target manually:"
    warn "  GFX_OVERRIDE=gfx1200 sudo bash $0"
    die "GPU detection failed"
fi

ok "GPU target : ${GFX}"
ok "Device index: HIP_VISIBLE_DEVICES=${HIP_DEVICE}  (discrete GPU)"

# RDNA4 = gfx120x — enables the PyTorch cross-attention optimisation
IS_RDNA4=false
[[ "$GFX" == gfx120* ]] && IS_RDNA4=true \
    && info "RDNA 4 detected — will set --use-pytorch-cross-attention"

# ── Step 1: Fix venv ownership ────────────────────────────────────────────────
section "Step 1/5 — Fixing venv ownership"
if [[ ! -d "$VENV" ]]; then
    die "venv not found at ${VENV}. Is the comfyui package installed?"
fi

VENV_OWNER=$(stat -c '%U' "$VENV")
if [[ "$VENV_OWNER" != "$COMFY_USER" ]]; then
    info "venv owned by '${VENV_OWNER}' — chowning to '${COMFY_USER}'..."
    chown -R "${COMFY_USER}:${COMFY_USER}" "$VENV"
    ok "venv ownership fixed"
else
    ok "venv ownership already correct"
fi

if [[ ! -d "$PIP_CACHE" ]]; then
    mkdir -p "$PIP_CACHE"
    info "Created pip-cache directory: ${PIP_CACHE}"
fi
chown -R "${COMFY_USER}:${COMFY_USER}" "$PIP_CACHE"
ok "pip-cache ownership fixed"

# ComfyUI writes to these dirs at runtime — all must be owned by comfy.
# (user settings, custom nodes, models, I/O staging, temp cache, DB)
# The AUR package installs everything as root; fix the writable subdirs here.
for WRITABLE_DIR in user custom_nodes models input output temp alembic_db; do
    DIR_PATH="${COMFY_HOME}/${WRITABLE_DIR}"
    mkdir -p "$DIR_PATH"
    chown -R "${COMFY_USER}:${COMFY_USER}" "$DIR_PATH"
    ok "Writable dir ready: ${DIR_PATH}"
done

# ── Step 2: Install PyTorch (ROCm) ───────────────────────────────────────────
section "Step 2/5 — Installing PyTorch for ROCm 7.2"
info "Downloading ~6 GB from ${ROCM_INDEX} — please be patient..."

sudo -u "${COMFY_USER}" "${VENV}/bin/pip" install \
    --cache-dir "${PIP_CACHE}" \
    --index-url "${ROCM_INDEX}" \
    torch torchvision torchaudio

ok "PyTorch ROCm build installed"

# ── Step 3: Install ComfyUI requirements ─────────────────────────────────────
section "Step 3/5 — Installing ComfyUI requirements"
sudo -u "${COMFY_USER}" "${VENV}/bin/pip" install \
    --cache-dir "${PIP_CACHE}" \
    --extra-index-url "${ROCM_INDEX}" \
    -r "${COMFY_HOME}/requirements.txt"

ok "ComfyUI requirements installed"

# ── Step 4: GPU group membership ─────────────────────────────────────────────
# rocm-install-arch.md §2: sudo usermod -aG render,video $USER
section "Step 4/5 — GPU group membership"
for GRP in render video; do
    if getent group "$GRP" &>/dev/null; then
        if ! id -nG "${COMFY_USER}" | grep -qw "$GRP"; then
            usermod -aG "$GRP" "${COMFY_USER}"
            ok "Added '${COMFY_USER}' to group '${GRP}'"
        else
            ok "'${COMFY_USER}' already in group '${GRP}'"
        fi
    else
        warn "Group '${GRP}' does not exist — skipping"
    fi
done
warn "Group changes take effect on next login / service restart"

# ── Step 5: Systemd service override ─────────────────────────────────────────
section "Step 5/5 — Systemd service configuration"
mkdir -p "$(dirname "$SERVICE_OVERRIDE")"

# rocm-install-arch.md §3: HSA_OVERRIDE_GFX_VERSION is NOT needed on ROCm 7.2
# for gfx1200 — ROCm identifies the RX 9060 XT correctly without it.
#
# rocm-install-arch.md §5: HIP_VISIBLE_DEVICES=0 pins the discrete card.
# Both the RX 9060 XT and Ryzen 9600X iGPU report as gfx1200; without this
# flag, the service may pick up the wrong device.
EXTRA_ARGS="--use-split-cross-attention"
$IS_RDNA4 && EXTRA_ARGS="--use-pytorch-cross-attention"

if [[ ! -f "$SERVICE_OVERRIDE" ]]; then
    cat > "$SERVICE_OVERRIDE" <<EOF
# ComfyUI ROCm service override
# Generated by fix-comfyui-rocm.sh
# GPU: ${GFX} (HIP device index: ${HIP_DEVICE})
# HSA_OVERRIDE_GFX_VERSION is intentionally omitted — ROCm 7.2 natively
# identifies gfx1200 (RX 9060 XT) without it. See rocm-install-arch.md §3.
[Service]
Environment=HIP_VISIBLE_DEVICES=${HIP_DEVICE}
Environment=ROCM_PATH=/opt/rocm
ExecStart=
ExecStart=/usr/bin/comfyui --listen 127.0.0.1 ${EXTRA_ARGS}
EOF
    ok "Created service override: ${SERVICE_OVERRIDE}"
else
    warn "Service override already exists — skipping (edit manually if needed)"
    warn "  ${SERVICE_OVERRIDE}"
fi

systemctl daemon-reload
ok "systemd daemon reloaded"

# ── Verification ──────────────────────────────────────────────────────────────
# rocm-install-arch.md §7: verify GPU is visible and is the discrete card
section "Verification"

info "Checking rocm-smi..."
if command -v rocm-smi &>/dev/null; then
    sudo -u "${COMFY_USER}" rocm-smi 2>/dev/null || rocm-smi 2>/dev/null || warn "rocm-smi failed (may need re-login for render group)"
else
    warn "rocm-smi not found — skipping"
fi

info "Testing PyTorch ROCm GPU detection (HIP_VISIBLE_DEVICES=${HIP_DEVICE})..."

VERIFY_OUT=$(HIP_VISIBLE_DEVICES="${HIP_DEVICE}" \
    sudo -u "${COMFY_USER}" "${VENV}/bin/python" - <<'PYEOF'
import torch, sys, os
hip  = torch.version.hip
cuda = torch.version.cuda
avail = torch.cuda.is_available()
name  = torch.cuda.get_device_name(0) if avail else "N/A"
dev   = os.environ.get("HIP_VISIBLE_DEVICES", "?")
print(f"  HIP version        : {hip}")
print(f"  CUDA version       : {cuda}  (None = ROCm build ✓)")
print(f"  GPU available      : {avail}")
print(f"  Device name        : {name}")
print(f"  HIP_VISIBLE_DEVICES: {dev}")
if not avail:
    sys.exit(1)
if cuda is not None:
    print("  WARNING: CUDA build detected instead of ROCm build!")
    sys.exit(2)
PYEOF
)
echo "$VERIFY_OUT"

if echo "$VERIFY_OUT" | grep -q "GPU available.*: True"; then
    ok "PyTorch sees the ROCm GPU ✓"
else
    warn "GPU not detected — try re-logging in so render/video group takes effect"
    warn "Then: sudo systemctl restart comfyui"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo
echo -e "${BOLD}${GREEN}══ All done! ══${RESET}"
echo
echo -e "  Start ComfyUI :  ${CYAN}sudo systemctl start comfyui${RESET}"
echo -e "  Enable on boot:  ${CYAN}sudo systemctl enable comfyui${RESET}"
echo -e "  Watch logs    :  ${CYAN}sudo journalctl -fu comfyui${RESET}"
echo -e "  Monitor GPU   :  ${CYAN}watch -n 1 rocm-smi${RESET}"
echo -e "  Web UI        :  ${CYAN}http://127.0.0.1:8188${RESET}"
echo
echo -e "${YELLOW}If your own account also needs GPU access:${RESET}"
echo -e "  ${CYAN}sudo usermod -aG render,video \$USER && newgrp render${RESET}"
echo
echo -e "${YELLOW}Dual-GPU note (RX 9060 XT + Ryzen 9600X iGPU both show as gfx1200):${RESET}"
echo -e "  The service is configured with ${CYAN}HIP_VISIBLE_DEVICES=${HIP_DEVICE}${RESET} (discrete card)."
echo -e "  Use ${CYAN}rocm-smi --showid${RESET} to confirm the correct index."
