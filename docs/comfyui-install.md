# ComfyUI installation notes

[Documentation index](README.md) · [Verified local ROCm 10 record](rocm-install-arch.md)

The following are copied upstream installation notes, retained as a reference and not verified here for the local ROCm 10 setup. [fix-comfyui-rocm.sh](fix-comfyui-rocm.sh) is a legacy ROCm 7.2 helper for `/opt/comfyui`.

## Manual install (Windows, Linux)

Python 3.14 works but some custom nodes may have issues. The free threaded variant works but some dependencies will enable the GIL so it's not fully supported.

Python 3.13 is very well supported. If you have trouble with some custom node dependencies on 3.13 you can try 3.12

torch 2.4 and above is supported but some features and optimizations might only work on newer versions. We generally recommend using the latest major version of pytorch with the latest cuda version unless it is less than 2 weeks old.

Instructions:
Git clone this repo.

Put your SD checkpoints (the huge ckpt/safetensors files) in: models/checkpoints

Put your VAE in: models/vae

## AMD GPUs (Linux)

AMD users can install rocm and pytorch with pip if you don't have it already installed, this is the command to install the stable version:

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm7.2
```

This is the command to install the nightly with ROCm 7.2 which might have some performance improvements:

```bash
pip install --pre torch torchvision torchaudio --index-url https://download.pytorch.org/whl/nightly/rocm7.2
```

## AMD GPUs (Experimental: Windows and Linux), RDNA 3, 3.5 and 4 only.

These have less hardware support than the builds above but they work on windows. You also need to install the pytorch version specific to your hardware.

RDNA 3 (RX 7000 series):

```bash
pip install --pre torch torchvision torchaudio --index-url https://rocm.nightlies.amd.com/v2/gfx110X-all/
```

RDNA 3.5 (Strix halo/Ryzen AI Max+ 365):

```bash
pip install --pre torch torchvision torchaudio --index-url https://rocm.nightlies.amd.com/v2/gfx1151/
```

RDNA 4 (RX 9000 series):

```bash
pip install --pre torch torchvision torchaudio --index-url https://rocm.nightlies.amd.com/v2/gfx120X-all/
```

## Intel GPUs (Windows and Linux)

Intel Arc GPU users can install native PyTorch with torch.xpu support using pip. More information can be found here

To install PyTorch xpu, use the following command:
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/xpu
```

This is the command to install the Pytorch xpu nightly which might have some performance improvements:

```bash
pip install --pre torch torchvision torchaudio --index-url https://download.pytorch.org/whl/nightly/xpu
```

## NVIDIA

Nvidia users should install stable pytorch using this command:

```bash
pip install torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu130
```

This is the command to install pytorch nightly instead which might have performance improvements.

```bash
pip install --pre torch torchvision torchaudio --index-url https://download.pytorch.org/whl/nightly/cu132
```

## Troubleshooting

If you get the "Torch not compiled with CUDA enabled" error, uninstall torch with:

```bash
pip uninstall torch
```

And install it again with the command above.

## Dependencies

Install the dependencies by opening your terminal inside the ComfyUI folder and:

```bash
pip install -r requirements.txt
```

After this you should have everything installed and can proceed to running ComfyUI.

## Other platforms

### Apple Mac silicon

You can install ComfyUI in Apple Mac silicon (M1, M2, M3 or M4) with any recent macOS version.

Install pytorch nightly. For instructions, read the Accelerated PyTorch training on Mac Apple Developer guide (make sure to install the latest pytorch nightly).
Follow the ComfyUI manual installation instructions for Windows and Linux.
Install the ComfyUI dependencies. If you have another Stable Diffusion UI you might be able to reuse the dependencies.
Launch ComfyUI by running python main.py
Note: Remember to add your models, VAE, LoRAs etc. to the corresponding Comfy folders, as discussed in ComfyUI manual installation.

### Ascend NPUs

For models compatible with Ascend Extension for PyTorch (torch_npu). To get started, ensure your environment meets the prerequisites outlined on the installation page. Here's a step-by-step guide tailored to your platform and installation method:

Begin by installing the recommended or newer kernel version for Linux as specified in the Installation page of torch-npu, if necessary.
Proceed with the installation of Ascend Basekit, which includes the driver, firmware, and CANN, following the instructions provided for your specific platform.
Next, install the necessary packages for torch-npu by adhering to the platform-specific instructions on the Installation page.
Finally, adhere to the ComfyUI manual installation guide for Linux. Once all components are installed, you can run ComfyUI as described earlier.

### Cambricon MLUs

For models compatible with Cambricon Extension for PyTorch (torch_mlu). Here's a step-by-step guide tailored to your platform and installation method:

Install the Cambricon CNToolkit by adhering to the platform-specific instructions on the Installation
Next, install the PyTorch(torch_mlu) following the instructions on the Installation
Launch ComfyUI by running python main.py

### Iluvatar Corex

For models compatible with Iluvatar Extension for PyTorch. Here's a step-by-step guide tailored to your platform and installation method:

Install the Iluvatar Corex Toolkit by adhering to the platform-specific instructions on the Installation
Launch ComfyUI by running python main.py

## ComfyUI-Manager

ComfyUI-Manager is an extension that allows you to easily install, update, and manage custom nodes for ComfyUI.

### Setup

Install the manager dependencies:

```bash
pip install -r manager_requirements.txt
```
Enable the manager with the --enable-manager flag when running ComfyUI:

```bash
python main.py --enable-manager
```

### Command Line Options

| Flag | Description |
| --- | --- |
| `--enable-manager` | Enable ComfyUI-Manager |
| `--enable-manager-legacy-ui` | Use the legacy manager UI instead of the new UI (implies `--enable-manager`) |
| `--disable-manager-ui` | Disable the manager UI and endpoints while keeping background features like security checks and scheduled installation completion (requires `--enable-manager`) |

## Running

```bash
python main.py
```

## For AMD cards not officially supported by ROCm

Try running it with this command if you have issues:

For 6700, 6600 and maybe other RDNA2 or older: HSA_OVERRIDE_GFX_VERSION=10.3.0 python main.py

For AMD 7600 and maybe other RDNA3 cards: HSA_OVERRIDE_GFX_VERSION=11.0.0 python main.py

## AMD ROCm Tips

You can try setting this env variable PYTORCH_TUNABLEOP_ENABLED=1 which might speed things up at the cost of a very slow initial run.

## Notes

Only parts of the graph that have an output with all the correct inputs will be executed.

Only parts of the graph that change from each execution to the next will be executed, if you submit the same graph twice only the first will be executed. If you change the last part of the graph only the part you changed and the part that depends on it will be executed.

Dragging a generated png on the webpage or loading one will give you the full workflow including seeds that were used to create it.

You can use () to change emphasis of a word or phrase like: (good code:1.2) or (bad code:0.8). The default emphasis for () is 1.1. To use () characters in your actual prompt escape them like \( or \).

You can use {day|night}, for wildcard/dynamic prompts. With this syntax "{wild|card|test}" will be randomly replaced by either "wild", "card" or "test" by the frontend every time you queue the prompt. To use {} characters in your actual prompt escape them like: \{ or \}.

Dynamic prompts also support C-style comments, like // comment or /* comment */.

To use a textual inversion concepts/embeddings in a text prompt put them in the models/embeddings directory and use them in the CLIPTextEncode node like this (you can omit the .pt extension):

embedding:embedding_filename.pt

## How to show high-quality previews?

Use --preview-method auto to enable previews.

The default installation includes a fast latent preview method that's low-resolution. To enable higher-quality previews with TAESD, download the taesd_decoder.pth, taesdxl_decoder.pth, taesd3_decoder.pth and taef1_decoder.pth and place them in the models/vae_approx folder. Once they're installed, restart ComfyUI and launch it with --preview-method taesd to enable high-quality previews.

## How to use TLS/SSL?

Generate a self-signed certificate (not appropriate for shared/production use) and key by running the command: openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -sha256 -days 3650 -nodes -subj "/C=XX/ST=StateName/L=CityName/O=CompanyName/OU=CompanySectionName/CN=CommonNameOrHostname"

Use --tls-keyfile key.pem --tls-certfile cert.pem to enable TLS/SSL, the app will now be accessible with https://... instead of http://....

Note: Windows users can use alexisrolland/docker-openssl or one of the 3rd party binary distributions to run the command example above.

If you use a container, note that the volume mount -v can be a relative path so ... -v ".\:/openssl-certs" ... would create the key & cert files in the current directory of your command prompt or powershell terminal.

## Support and dev channel

Discord: Try the #help or #feedback channels.

Matrix space: #comfyui_space:matrix.org (it's like discord but open source).

See also: https://www.comfy.org/

psst — we're hiring! Help build ComfyUI: comfy.org/careers

## Frontend Development

As of August 15, 2024, we have transitioned to a new frontend, which is now hosted in a separate repository: ComfyUI Frontend. The compiled JS files (from TS/Vue) are published to pypi and installed as a dependency in ComfyUI.

## Reporting Issues and Requesting Features

For any bugs, issues, or feature requests related to the frontend, please use the ComfyUI Frontend repository. This will help us manage and address frontend-specific concerns more efficiently.

## Using the Latest Frontend

The new frontend is now the default for ComfyUI. However, please note:

The frontend in the main ComfyUI repository is updated fortnightly.
Daily releases are available in the separate frontend repository.
To use the most up-to-date frontend version:

For the latest daily release, launch ComfyUI with this command line argument:

--front-end-version Comfy-Org/ComfyUI_frontend@latest
For a specific version, replace latest with the desired version number:

--front-end-version Comfy-Org/ComfyUI_frontend@1.2.2
This approach allows you to easily switch between the stable fortnightly release and the cutting-edge daily updates, or even specific versions for testing purposes.
