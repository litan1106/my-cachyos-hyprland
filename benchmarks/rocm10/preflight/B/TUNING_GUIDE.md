# BFS tuning guide: improve likeness, motion, and face integration

Use this with the [step-by-step user guide](USER_GUIDE.md). It applies to the installed **V3 / LTX-2.3** workflow on the RX 9060 XT.

The practical order is: **reference and source quality → prompt cleanup → small LoRA comparisons → working resolution → duration → final export**. Work on the visible defect before spending more memory on a bigger render.

## What has actually been tested

| Comparison | Observed result on the public Sintel sample |
| --- | --- |
| Adaptive V3 LoRA at 1.0 | Working baseline; visible reference influence, coherent hair/jaw, but stylized facial features and reduced mouth opening. |
| Same inputs, prompt and seed; strength 0.8 | Weaker reference features and a more source-like face. Mouth opening was not restored. |
| Strength 1.0; remove the reference's closed-mouth wording | Small visual change; mouth opening still not restored. |

See the [measured results](README.md#tested-sample-and-limits) and [run records](benchmarks/results.jsonl). None of these is an accepted best-quality preset. The extra trial values below are **proposed experiments**, not measured improvements or author-prescribed settings.

## 1. Make comparisons repeatable

1. Save a separate copy of the adapted workflow for your experiment. Keep the upstream workflow unchanged.
2. Use the same continuous segment and reference image. For the historical smoke workload, prepare a 33-frame input; the saved workflows now load the full input without a frame cap.
3. Find **RandomNoise**. Keep its `noise_seed` unchanged and switch its seed-control dropdown from **randomize** to **fixed**. The saved browser workflow currently uses `randomize`; set this explicitly before comparing runs.
4. Keep the prompt, resolution, FPS, model files, sampler, and frame range unchanged except for the single factor being tested.
5. Save a baseline video, then make one change and save a separate candidate video.
6. Compare the same frames and play both clips at normal speed.

For exact reproduction of the original sample seed, use `1035625245488400`. Once a candidate looks better, try another seed and another shot separately to check whether the improvement holds.

Name experiments clearly, for example `reference-crop-A`, `strength-095`, and `strength-105`. These names describe trials; they do not establish quality.

## 2. Improve the reference before changing model settings

In **Face Reference**, try a different crop of the same original photo as one experiment:

- Make the head occupy most of the image while retaining the full jaw, ears where visible, and hairstyle.
- Use an original with clear facial detail rather than enlarging a blurry thumbnail.
- Prefer a pose and lighting direction reasonably close to the source shot.
- Avoid a hand, object, or heavy shadow hiding the defining features you need transferred.
- If the source has major turns, test a suitable reference angle separately instead of judging only a frontal frame.

This is a proposed input comparison, not a guarantee that a tighter crop wins. Check that the crop still contains the head and hair you want.

The reference is fitted into a small side panel, so a full-body reference can leave very few pixels for the face. The [prepared baseline guide](logs/prepared-guide.png) illustrates how much of the reference is actually visible.

### Use two reference photos

Load [bfs-v3-rx9060xt-x.json](workflows/bfs-v3-rx9060xt-x.json) in ComfyUI for the experimental two-photo variant. The original single-photo workflow remains available.

1. Upload a frontal portrait in **Face Reference 1 - frontal**.
2. Upload another view of the **same person** in **Face Reference 2 - same person, another angle**. A three-quarter view is a useful first experiment. Both selectors initially use `reference.png` as a placeholder; replace them before comparing.
3. Use similar head crops and image aspect ratios. **Combine two face references** resizes and center-crops the second image to the first image's dimensions when they differ, so check that hair and jaw are retained.
4. Keep the composer on `all_faces_every_frame` and `vertical`. Both photos stay in the left panel throughout the guide; the workflow does not alternate them.
5. Edit the same **FACE / ACTION** prompt as in the single-photo guide. Describe the shared identity under FACE, without describing the panel or photo layout.
6. Run the selected source segment; this workflow now loads the full input without a frame cap or fixed audio trim. This variant starts with the same seed set to **fixed**, and saves numbered `bfs-multiref_*.mp4` files.

Compare photo A alone, photo B alone, and A+B using the same seed, prompt, video range and other settings. In the 128 × 320 panel, padding and spacing leave two slots up to 104 × 142 pixels each. More views can reduce detail per view, so multiple photos are not automatically better. Keep the panel width, canvas padding and source offset coordinated if changing geometry.

This is an inference-conditioning experiment, not model training. Node registration, browser import/export, and CPU guide composition have been checked; a two-photo model render and improved likeness have **not** been verified. The CPU guide check uses the sample portrait twice to check wiring, not to establish a multi-view benefit. See [verification](logs/multiref-verification.json). The companion [API graph](workflows/bfs-v3-rx9060xt-x-api.json) is intended for custom automation; the current command-line runner exposes only one reference-upload argument.

## 3. Clean up the V3 prompt

The [author's V3 instructions](https://huggingface.co/Alissonerdx/BFS-Best-Face-Swap-Video) separate reference identity from the main video's body performance. Derive **FACE** only from the reference. Under **ACTION**, call the performer “a person” and describe body actions, clothing, objects, camera, and environment. Exclude the source face/head appearance and facial-expression descriptions. Leave panel/editing terminology out of the caption.

An author-aligned example for the sample is:

```text
head_swap:

FACE:
An adult woman with light skin, an oval face, hazel-brown eyes, and medium curly brown hair.

ACTION:
A person in a sleeveless top is seated in a dim, warm-lit room. The camera holds a close view of the upper body with slight body movement.
```

This revised template follows the author's prompt boundary; it has **not** been tested as a new local quality improvement. The previously rendered captions included facial-motion wording in ACTION.

Keep identity details factual and visible. Remove contradictory descriptions, invented traits, and expressions imported from the still photo. Change the prompt as its own experiment; keep strength and seed fixed.

The local closed-mouth-removal trial did not restore expression. If a cleaned prompt still produces a frozen mouth, record that result and inspect the source, reference, and guide rather than repeatedly adding prompt adjectives.

## 4. Adjust LoRA strength in small steps

Find **LoraLoaderModelOnly**, select the existing adaptive V3 file, and adjust **strength_model**. The starting value is **1.0**.

| Trial | Purpose | Evidence status |
| --- | --- | --- |
| 1.0 | Baseline comparison point | Rendered locally. |
| 0.95 | Small reduction to test integration and performance preservation | Untested proposal. |
| 1.05 | Small increase to test reference influence | Untested proposal. |
| 0.8 | Larger reduction already compared | Weakened likeness on the sample; not a recommended default. |

Run each proposed value separately against the baseline. Increasing strength can change the whole reconstruction; judge motion and scene preservation as well as likeness. Stop increasing it if the face becomes distorted or the performance degrades. Lowering strength is not a reliable VRAM-saving technique.

Keep the same LoRA file while testing strength. Switching to rank64 is a different model experiment and should have its own record.

## 5. Match the tweak to the defect

These are next tests to investigate, not promised fixes.

| What you see | First thing to inspect | Next controlled trial |
| --- | --- | --- |
| Face barely resembles the reference | Reference clarity, crop, and visible head size in the panel | Compare another crop; then a small strength change separately. |
| Source hair or facial identity remains | Caption accidentally describes the source head; reference is too small or obscured | Clean the prompt or change the reference, one at a time. |
| Large head, distorted jaw, or odd eyes | Reference pose/proportions and composed-guide geometry | Compare a better-matched reference; then a small strength reduction separately. |
| Mouth or expression is frozen | Source performance, reference expression, caption conflicts | Clean the V3 caption as a separate trial; inspect paired frames. Prompt changes alone did not fix the local sample. |
| Identity changes or flickers | Scene cuts, occlusions, inconsistent guide preparation | Use a continuous shot and inspect difficult frames before tuning strength. |
| Face is blurry | Actual facial pixels in the reference and source | Improve input detail first; test a larger working resolution only with memory headroom. |
| Hair/jaw edges look pasted or lighting does not match | Reference lighting, pose, and crop | Compare a more compatible reference. Extra sharpening cannot repair alignment. |
| Green panel remains or framing is wrong | Correct V3 workflow, panel geometry, and guide connections | Restore the baseline geometry before changing quality controls. |
| OOM, heavy swapping, or very slow repeated jobs | GPU/host memory and cache history | Restart the project server when idle; reduce one workload factor and revalidate before judging quality. |

## 6. Advanced reference-panel controls

In **ReservedRegionFrameComposer**, the current defaults include:

| Control | Current value | What to check when experimenting |
| --- | ---: | --- |
| `face_scale_pct` | 100 | Enlarging the reference can clip the head or overflow its intended placement. Inspect a new guide preview. |
| `face_padding_px` | 12 | Smaller padding leaves more room for the reference; verify borders, alignment, and clipping. |
| `region_size_px` | 128 | Changing panel width changes the composed canvas and memory workload. |

Try reference cropping first. Scale/padding changes are untested quality experiments. The saved guide image shows only the baseline; it does not preview your new settings.

Panel width is linked geometrically to **Expand canvas for reference panel** (`ImagePadForOutpaint.left`) and **Restore exact 512 x 320 source area** (`ImageCompositeMasked.x`). All three are currently **128**. A panel-width experiment must coordinate those values and validate the resulting dimensions and source placement together. Keep the V3 green-panel semantics and reference persistence intact.

Use V3 preparation for this workflow. V2's magenta-mask and first-frame recipes belong to a separate workflow comparison.

## 7. Keep these controls unchanged initially

| Control | Baseline | Reason |
| --- | --- | --- |
| `CFGGuider.cfg` | 1.0 | Part of the inspected distilled workflow; changing CFG is a separate sampling experiment. |
| `ManualSigmas` | Saved nine values, giving eight steps | Values materialize the chosen scheduler curve. More entries or steps are not a generic quality upgrade. |
| Sampler | `euler_ancestral_cfg_pp` | Keep the baseline while tuning inputs and strength. |
| Guide strength | 1.0 | The guide contains both reference identity and source performance; it is not a source-face-only control. |
| Tiled decode settings | Saved defaults | Memory/decoding controls; changing tiles does not directly strengthen identity. |
| Model family and quantization | LTX-2.3 Q3 + Gemma Q4 | Different precision or model files require a separate compatibility, memory, and quality comparison. |

Do not change CFG, steps, sampler, strength, and resolution together. A good-looking result would leave you unable to tell which change helped.

## 8. Review and record the result

Inspect start, middle, end, blinks, mouth movement, turns, and occlusions. For the 33-frame baseline, frames **0, 16, and 32** are useful anchors; frames **8–12** cover the observed blink. Play the video as well as looking at stills.

Use a simple comparison note:

| Field | Your entry |
| --- | --- |
| Baseline / candidate filenames | |
| Source range, reference, and seed | |
| Single changed factor; old → new | |
| Likeness | |
| Mouth, blink, and motion fidelity | |
| Hair/jaw edges and proportions | |
| Flicker, drift, and difficult frame/time | |
| Scene, framing, panel removal, and audio | |
| Time, memory/swap observations, or failure | |
| Keep or reject, with reason | |

Browser runs do not automatically populate the command-line runner's benchmark records. Save your workflow copy, output, and notes. The optional runner and review commands are in the [README](README.md).

## 9. Increase resolution and duration only after quality improves

Keep duration fixed while testing resolution, then test duration separately. Check actual output dimensions and playback after each change. The tested small jobs already used about 15.2–15.3 GiB of sampled GPU memory and process swap, so larger working resolutions are not established presets.

Portrait layout, 49/97-frame runs, higher precision, restoration/inpainting, and additional generation passes remain separate, unvalidated experiments. The current sample is human-to-animation and very short; a change that helps it may not help a real-person talking shot. Upscale for delivery only after the underlying swap is acceptable.

## Sources and local procedures

- [Author's model guide, especially V3 preparation and prompting](https://huggingface.co/Alissonerdx/BFS-Best-Face-Swap-Video).
- [Local tuning procedure](.agent/skills/bfs-tune-workflow/SKILL.md) and [output-review procedure](.agent/skills/bfs-review-output/SKILL.md).
- [Baseline run](benchmarks/runs/bfs-smoke/result.json), [strength-0.8 comparison](benchmarks/runs/bfs-lora08/result.json), and [prompt comparison](benchmarks/runs/bfs-prompt-motion-retry/result.json).
- [Baseline composed guide](logs/prepared-guide.png) and [ordered output face frames](benchmarks/contact-sheets/bfs-smoke-all-face-frames.png).
