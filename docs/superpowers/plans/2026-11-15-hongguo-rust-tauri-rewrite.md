# Hongguo Native Client (Rust + Tauri) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Python backend, host-JVM signer, and external browser launcher with one Rust/Tauri 2 application (`hongguo-desktop`) that keeps the current viewing features and improves episode transitions.

**Architecture:** A Cargo workspace under `apps/hongguo/` with `hongguo-core` (API, caches, media preparation), `hongguo-signer` (in-process ARM64 emulation of the Android signing library), and a Tauri 2 shell. The UI calls typed Tauri commands; video reaches the WebKitGTK `<video>` element through an asynchronous custom protocol with HTTP Range support. Signing state, credentials, and media preparation stay in Rust.

**Tech Stack:** Rust 1.99 (system), Tokio, reqwest, rusqlite, Tauri 2, WebKitGTK 4.1 + GStreamer 1.28 (system), `unicorn-engine` crate (primary emulator candidate), Node test runner for UI tests.

**User decisions (already made):**
- System WebKitGTK/GStreamer libraries are acceptable dependencies.
- Target is one application binary with embedded assets, no Python or JVM runtime, and no external browser; normal WebKit helper processes are fine; a static binary or single OS process is not required.
- Shipping the Java signer or delegating signing to a remote service does not meet the target.
- Guest access only; account login and cloud history are separate work.
- The working native installation stays usable throughout; the default launcher changes only after the acceptance results are reviewed.
- Build-time and reference-test tools may use Python, Java, or Node; the installed app must not.

---

## Scope and execution rule

Tasks 2 and 3 are feasibility gates. Tasks 4–8 depend on choices those gates make (emulator binding, remux strategy, codec path). **After Tasks 2 and 3 pass, re-run the writing-plans skill on Tasks 4–8 to replace their discovery steps with code-level steps before executing them.** If either gate fails, stop and revise this plan with the user.

Do not push during execution. Commit per task on a feature branch.

## Verified starting point (audited 2026-11-15)

Repository:
- UI: `scripts/hongguo-web/index.html` — calls `/latest`, `/rank`, `/search`, `/episodes`, `/img`, and plays `/stream?series_id=&ep=`. It is the UI the launcher serves (`install-hongguo.sh:91`); the stock `backend/web/index.html` differs and is not used.
- Autoplay regression tests: `tests/test_hongguo_player.cjs` (6 tests), committed in `d13f06e`.
- Launcher/installer: `scripts/launch-hongguo.sh`, `scripts/install-hongguo.sh`, `scripts/hongguo-common.sh`, `scripts/remove-hongguo.sh`.
- Persistent cache wrapper: `scripts/hongguo-web/standalone_server.py` (SQLite rows holding pickled values; cover JPEGs on disk).

Installed reference backend, `~/.local/share/hongguo-native/backend/`:
- `hongguo.py` — API client. `sign()` POSTs `{"url", "headers"}` to `$SIGN_SERVER/sign` and merges the returned headers. List endpoints (`/reading/bookapi/bookmall/cell/change/v`, `/reading/distribution/category/landpage/v`) are sent **unsigned** unless `HG_SIGN_LIST=1`. `refresh_session()` calls `/grab`, but `FqTrace` only serves `/sign`, so session refresh is effectively absent today.
- `server.py` `/stream` → `_ensure_decrypted()` → `offline_dl`/`frida/offline_decrypt.py`, then, because the launcher sets `HONGGUO_SESSION_API_KEY`, **always** `desktop_encode.encode_h264()` (libx264 ultrafast, CRF 20).
- `frida/unwrap_spade.py` — v1 spade unwrap only; v2 (`app_v2`/`web_v2`, AES-GCM) returns `None`. `offline_decrypt` tries `flag` then `1-flag`, validates the key/IV by NAL check (`oracle.verify_key_iv`), decrypts AES-128-CTR per track using each track's `senc` base IV, then `decutil.remux_playable` (ffmpeg CLI) strips CENC signalling; `desktop_remux.remux` (PyAV) sets `hvc1`/`mp4a` tags and `+faststart`.
- `desktop_quality.choose_desktop_track()` — picks highest short-edge resolution, then size; used as quality `desktop-resolution-v1` by the HLS route.
- `desktop_hls_service.py` router is mounted (launcher sets `HONGGUO_HLS_WORK_DIR`) but **the repo UI never calls it**. Out of scope.
- Signer: `sign/unidbg-sign.jar` (unidbg + Unicorn backend) with classes `FqTrace`, `MetasecSign`, `EncryptRun`. `capture/fq_oversea/` holds AArch64 `libmetasec_ml.so`, `libc++_shared.so`, `ms_16777218.bin`.
- `libmetasec_ml.so` NEEDS `liblog.so libandroid.so libm.so libdl.so libc.so`. unidbg supplies these from its bundled Android SDK 23 bionic images (`android/sdk23/lib64/*.so` in the jar) plus virtual modules. **The Rust signer must load or stub these too.**

Evidence on this machine:
- All 5 cached source episodes (`~/.local/share/hongguo-native/data/stream-cache/*_best.mp4`) are **HEVC + AAC**, 1080p. Their H.264 re-encodes are 10–17× larger (e.g. 13.0 MB → 218.4 MB).
- GStreamer has `vah265dec` (VA-API, RX 9060 XT), `avdec_h265`, and `libde265dec`. Packages: `webkit2gtk-4.1 2.54.2`, `gstreamer`/`gst-plugins-{good,bad}`/`gst-libav 1.28.9`, `ffmpeg 9.0.2`, `libheif 1.23.7`.
- Installed: `bwrap`. Not installed: `tauri-driver`, `WebKitWebDriver`, `strace`, `namcap` (dev-only tools for Tasks 5, 7, 8 — install with `sudo pacman -S strace namcap`), `unicorn` (not needed if the crate builds it).

Signer reference source: [unidbg-sign at 5f8a58d](https://github.com/zhangbaio/hongguo/tree/5f8a58d10f48954bc9b6a58c9cd6418bf499feb9/unidbg-sign/src/main/java/com/hongguo/sign) — read `FqTrace.java`, `MetasecSign.java`, and `EncryptRun.java`.

Tauri references: [process model](https://v2.tauri.app/concept/process-model/), [Rust commands](https://v2.tauri.app/develop/calling-rust/), [Linux prerequisites](https://v2.tauri.app/start/prerequisites/), [streaming example](https://github.com/tauri-apps/tauri/blob/dev/examples/streaming/main.rs), [WebDriver](https://v2.tauri.app/develop/tests/webdriver/).

## File structure

```
apps/hongguo/
  Cargo.toml                      workspace
  README.md
  crates/hongguo-core/            models, api, catalog, config, cache, images, media/*
  crates/hongguo-signer/          ELF loader, Android/JNI shims, emulator worker
  src-tauri/                      Tauri shell, media protocol, commands, state
  ui/                             index.html, app.js, api.js, player.js, styles.css
  resources/signer/manifest.json  pinned signer asset hashes
  tools/                          capture-reference.py, verify-runtime.sh
  tests/                          fixtures/, player.test.cjs, desktop-smoke.mjs
  packaging/PKGBUILD
  docs/baseline.md, docs/acceptance.md
```

---

### Task 1: Reference capture, baseline, and workspace

**Goal:** Capture reference responses and baseline timings from the running legacy app, and create the Cargo workspace with typed models that parse them.

**Files:**
- Create: `apps/hongguo/Cargo.toml`, `apps/hongguo/README.md`, `apps/hongguo/.gitignore`
- Create: `apps/hongguo/crates/hongguo-core/Cargo.toml`, `src/lib.rs`, `src/models.rs`
- Create: `apps/hongguo/crates/hongguo-core/tests/contracts.rs`
- Create: `apps/hongguo/tools/capture-reference.py`
- Create: `apps/hongguo/tests/fixtures/*.json` (committed, redacted), `apps/hongguo/tests/fixtures/local/` (gitignored)
- Create: `apps/hongguo/docs/baseline.md`

**Acceptance Criteria:**
- [ ] `docs/baseline.md` lists sha256 of `hongguo.py`, `server.py`, `offline_dl.py`, `frida/*.py`, `desktop_*.py`, `unidbg-sign.jar`, and the three `capture/fq_oversea/` files, plus the installer version (`v1.0.12`).
- [ ] Fixtures exist for latest, rank (recommend), search, episodes, and video_model; committed fixtures contain no `spade_a`, no CDN URLs with tokens, and no device/install IDs.
- [ ] `docs/baseline.md` records cold/warm startup, first-frame delay, episode-transition delay, CPU and RSS with episode IDs, cache state, and sample count (n ≥ 5).
- [ ] Contract tests parse every committed fixture.

**Verify:** `cargo test --manifest-path apps/hongguo/Cargo.toml -p hongguo-core --test contracts` → all pass; `grep -rE 'spade_a|install_id|device_id' apps/hongguo/tests/fixtures/*.json` → no output.

**Steps:**

- [ ] **Step 1: Workspace skeleton**

`apps/hongguo/Cargo.toml`:
```toml
[workspace]
resolver = "3"
members = ["crates/hongguo-core"]

[workspace.package]
edition = "2024"
license = "MIT"

[workspace.dependencies]
serde = { version = "1", features = ["derive"] }
serde_json = "1"
thiserror = "2"
tokio = { version = "1", features = ["rt-multi-thread", "macros", "sync", "time", "fs"] }
```

`apps/hongguo/.gitignore`:
```
/target
/tests/fixtures/local/
```

`crates/hongguo-core/Cargo.toml`:
```toml
[package]
name = "hongguo-core"
version = "0.1.0"
edition.workspace = true

[dependencies]
serde.workspace = true
serde_json.workspace = true
thiserror.workspace = true
```

- [ ] **Step 2: Write `tools/capture-reference.py`**

Run against the legacy backend started with `launch-hongguo --no-open` (prints the URL). Script requirements: stdlib only (`urllib`, `hashlib`, `json`); args `--base http://127.0.0.1:PORT --api-key KEY --series SID --query Q --out apps/hongguo/tests/fixtures`; writes raw responses to `fixtures/local/` and redacted copies (drop keys `spade_a`, `encrypted_url`, `backup`, `url`, `install_id`, `device_id`; replace with `"<redacted>"`) to `fixtures/`; prints the sha256 table for the files listed in the AC.

```python
REDACT = {"spade_a", "encrypted_url", "backup", "url", "install_id", "device_id"}

def redact(node):
    if isinstance(node, dict):
        return {k: ("<redacted>" if k in REDACT else redact(v)) for k, v in node.items()}
    if isinstance(node, list):
        return [redact(v) for v in node]
    return node
```

The video_model fixture is captured by calling `/play?series_id=SID&ep=1` (it returns `episodes[].definition/size/shape`).

- [ ] **Step 3: Write failing contract test**

```rust
// crates/hongguo-core/tests/contracts.rs
use hongguo_core::models::{EpisodeList, FeedPage, PlayInfo, SearchPage};

fn fixture(name: &str) -> String {
    std::fs::read_to_string(format!("{}/../../tests/fixtures/{name}", env!("CARGO_MANIFEST_DIR"))).unwrap()
}

#[test]
fn latest_parses() { let p: FeedPage = serde_json::from_str(&fixture("latest.json")).unwrap(); assert!(!p.items.is_empty()); }
#[test]
fn rank_parses() { let p: FeedPage = serde_json::from_str(&fixture("rank_recommend.json")).unwrap(); assert!(!p.items.is_empty()); }
#[test]
fn search_parses() { let p: SearchPage = serde_json::from_str(&fixture("search.json")).unwrap(); assert!(!p.items.is_empty()); }
#[test]
fn episodes_sorted_indices() {
    let e: EpisodeList = serde_json::from_str(&fixture("episodes.json")).unwrap();
    assert!(e.episodes.windows(2).all(|w| w[0].index <= w[1].index));
}
#[test]
fn play_parses() { let p: PlayInfo = serde_json::from_str(&fixture("play.json")).unwrap(); assert!(!p.episodes.is_empty()); }
```

Run: `cargo test --manifest-path apps/hongguo/Cargo.toml -p hongguo-core --test contracts` → FAIL (`models` missing).

- [ ] **Step 4: Implement `models.rs`** with `#[serde(default)]` on optional fields and field names taken from the captured fixtures (the UI reads `d.items || d.results`, so `SearchPage` uses `#[serde(alias = "results")]`). `lib.rs`: `pub mod models;`. Re-run → PASS.

- [ ] **Step 5: Baseline measurements** — record in `docs/baseline.md` using `hyperfine`-style repeated runs or a stopwatch log with `pidstat -r -u -p <pids> 1` for CPU/RSS of the Python backend + JVM + browser. Use the 5 episode IDs present in `stream-cache` for warm runs and 2 uncached episodes for cold runs.

- [ ] **Step 6: Commit** `git add apps/hongguo && git commit -m "hongguo: reference fixtures, baseline, core workspace"`

---

### Task 2: Prove signing works without Java (GATE)

**Goal:** A Rust-only signer, running in-process via ARM64 emulation of `libmetasec_ml.so`, produces headers the live service accepts for search, episodes, and video_model, with no Java installed in the runtime environment.

> **USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

**Files:**
- Modify: `apps/hongguo/Cargo.toml` (add member)
- Create: `apps/hongguo/crates/hongguo-signer/Cargo.toml`, `src/lib.rs`, `src/elf.rs`, `src/android.rs`, `src/jni.rs`, `src/worker.rs`
- Create: `apps/hongguo/crates/hongguo-signer/tests/compatibility.rs`, `tests/live_signing.rs`
- Create: `apps/hongguo/resources/signer/manifest.json`
- Create: `apps/hongguo/crates/hongguo-signer/NOTES.md` (JNI/syscall inventory)

**Acceptance Criteria:**
- [ ] `NOTES.md` lists every JNI method, syscall, file path, system property, and library symbol touched during init and one sign call, taken from the three Java classes and a unidbg trace run.
- [ ] `manifest.json` records sha256 for every embedded asset, including whichever Android SDK 23 bionic libraries are loaded (or states which are replaced by Rust stubs).
- [ ] Under a fixed clock and entropy, Rust and Java produce identical header sets for 3 recorded requests (`compatibility.rs`).
- [ ] `live_signing.rs` (ignored by default) gets HTTP 200 with `code == 0` for signed search, episodes, and video_model, run inside `env -i PATH=/usr/bin:/bin` with `java` not resolvable (`command -v java` fails in that env, `/usr/bin/java` resolves into `/usr/lib/jvm`, so masking that directory with `bwrap --tmpfs` breaks it).
- [ ] Signing a request takes < 200 ms p95 after warm-up; worker shutdown completes within 2 s.

**Verify:** `cargo test --manifest-path apps/hongguo/Cargo.toml -p hongguo-signer` → pass; `bwrap --dev-bind / / --tmpfs /usr/lib/jvm env -i PATH=/usr/bin:/bin HOME=$HOME cargo test --manifest-path apps/hongguo/Cargo.toml -p hongguo-signer --test live_signing -- --ignored` → 3 pass.

**Steps:**

- [ ] **Step 1: Inventory the reference.** Read the three Java classes at the pinned commit. Run the Java signer once with unidbg verbose logging (`-Dunidbg.verbose=true` or the class's trace flag) to list loaded modules, JNI calls, syscalls, and file opens. Write `NOTES.md`.

- [ ] **Step 2: Choose and pin the emulator binding.** Primary: `unicorn-engine` crate (same Unicorn core as unidbg's backend; builds the C library statically via its build script, so no runtime package dependency). Record the version in `Cargo.toml` and `manifest.json`. Fall back to an alternative only if Step 4 shows a Unicorn-specific blocker; record why.

- [ ] **Step 3: Define the signer interface (matches the current HTTP contract).**

```rust
// src/lib.rs
pub type Headers = Vec<(String, String)>; // order preserved

#[derive(Debug, thiserror::Error)]
pub enum SignError {
    #[error("signer initialisation failed: {0}")] Init(String),
    #[error("emulation fault: {0}")] Fault(String),
    #[error("signer timed out")] Timeout,
    #[error("signer stopped")] Stopped,
}

pub trait Sign: Send + Sync {
    /// Same inputs as legacy POST /sign {"url","headers"}; returns headers to merge.
    fn sign(&self, url: &str, headers: &Headers) -> Result<Headers, SignError>;
}
```

- [ ] **Step 4: Loader and Android shims.** `elf.rs`: AArch64 ELF64 loader with relocations (`R_AARCH64_RELATIVE`, `GLOB_DAT`, `JUMP_SLOT`, `ABS64`), init_array execution, symbol resolution across loaded modules. `android.rs`: load the bionic `libc.so`/`libdl.so`/`libm.so`/`liblog.so` from SDK 23 (extracted from the jar into `resources/signer/`, embedded with `include_bytes!`) or stub individual symbols; provide a `libandroid.so` stub module; syscall handler for the inventory from Step 1 with a virtual filesystem serving `ms_16777218.bin` and any `/proc`/`/system` paths listed. `jni.rs`: minimal JNIEnv/JavaVM function tables implementing only the calls in `NOTES.md`.

- [ ] **Step 5: Worker thread.** `worker.rs`: emulator owned by one dedicated thread; `std::sync::mpsc::sync_channel(32)` request queue; each request carries a `oneshot` reply; caller-side timeout 5 s → `SignError::Timeout`; `Drop` sends shutdown and joins.

- [ ] **Step 6: Deterministic compatibility test.** Add a `--fixed-clock <ms> --fixed-seed <n>` mode to a small Java harness under `apps/hongguo/tools/` (build-time only) and an equivalent `SignerConfig { clock, seed }` in Rust. Record 3 request/response pairs into `tests/fixtures/local/signer/` and assert equality in `compatibility.rs`. Header order must match.

- [ ] **Step 7: Live test.** `live_signing.rs` builds real search/episodes/video_model requests (reuse query construction from `hongguo.py`, guest config from `guest-config.json`), signs them, sends with reqwest, asserts HTTP 200 and JSON `code == 0`. Mark `#[ignore]`.

- [ ] **Step 8: Run verify commands; commit** `git commit -m "hongguo: in-process Rust signer"`.

**Gate:** If live acceptance fails after the JNI/syscall inventory is fully implemented, stop and report to the user with the failing request, response code, and the last emulated call. Do not ship the Java signer or a remote signer as a workaround.

---

### Task 3: Prove Tauri playback on CachyOS/Hyprland (GATE)

**Goal:** A minimal `hongguo-desktop` Tauri window plays the cached HEVC/AAC episodes through a custom Range-capable protocol with picture, sound, seek, fullscreen, and repeated source changes.

> **USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

**Files:**
- Modify: `apps/hongguo/Cargo.toml` (add `src-tauri` member)
- Create: `apps/hongguo/src-tauri/Cargo.toml`, `build.rs`, `tauri.conf.json`, `capabilities/main.json`
- Create: `apps/hongguo/src-tauri/src/main.rs`, `src/lib.rs`, `src/media_protocol.rs`, `src/range.rs`
- Create: `apps/hongguo/ui/index.html`, `ui/player.js`, `ui/styles.css`
- Create: `apps/hongguo/docs/playback-probe.md`

**Acceptance Criteria:**
- [ ] `range.rs` unit tests pass for `bytes=0-`, `bytes=100-199`, `bytes=-500`, `bytes=9999999-` (→ 416), multi-range (→ first range or 416, documented), and missing header (→ 200 full).
- [ ] The protocol serves only IDs registered in an in-memory map; a request for an unregistered ID or a path containing `/` or `..` returns 404.
- [ ] On this machine, `--playback-probe` plays each of the 5 cached `*_best.mp4` files (HEVC) with picture and sound, seeks to 50% and 90%, enters/leaves fullscreen, and switches source 20 times; `docs/playback-probe.md` records the result per file.
- [ ] `docs/playback-probe.md` names the decoder actually used (`GST_DEBUG=2,*decodebin*:4` log showing `vah265dec` or a software decoder) and the RSS of all hongguo-desktop + WebKit processes after the 20 switches (no monotonic growth across 3 repeats).
- [ ] The decision is recorded: direct HEVC playback works → no transcoding in Task 5; otherwise the exact failure and the chosen fallback.

**Verify:** `cargo test --manifest-path apps/hongguo/Cargo.toml -p hongguo-desktop range` → pass; `HONGGUO_PROBE_DIR=~/.local/share/hongguo-native/data/stream-cache cargo run --manifest-path apps/hongguo/Cargo.toml -p hongguo-desktop -- --playback-probe` → window plays; probe prints `PROBE OK <file>` per file.

**Steps:**

- [ ] **Step 1: Failing Range tests**

```rust
// src-tauri/src/range.rs
#[derive(Debug, PartialEq)]
pub enum RangeResult { Full, Partial { start: u64, end: u64 }, Unsatisfiable }

pub fn parse_range(header: Option<&str>, len: u64) -> RangeResult { todo!() }

#[cfg(test)]
mod tests {
    use super::*;
    use RangeResult::*;
    #[test] fn none_is_full() { assert_eq!(parse_range(None, 1000), Full); }
    #[test] fn open_end() { assert_eq!(parse_range(Some("bytes=0-"), 1000), Partial { start: 0, end: 999 }); }
    #[test] fn closed() { assert_eq!(parse_range(Some("bytes=100-199"), 1000), Partial { start: 100, end: 199 }); }
    #[test] fn clamps_end() { assert_eq!(parse_range(Some("bytes=900-5000"), 1000), Partial { start: 900, end: 999 }); }
    #[test] fn suffix() { assert_eq!(parse_range(Some("bytes=-500"), 1000), Partial { start: 500, end: 999 }); }
    #[test] fn suffix_larger_than_file() { assert_eq!(parse_range(Some("bytes=-5000"), 1000), Partial { start: 0, end: 999 }); }
    #[test] fn past_end() { assert_eq!(parse_range(Some("bytes=1000-"), 1000), Unsatisfiable); }
    #[test] fn garbage_is_full() { assert_eq!(parse_range(Some("items=1-2"), 1000), Full); }
    #[test] fn multi_takes_first() { assert_eq!(parse_range(Some("bytes=0-9,20-29"), 1000), Partial { start: 0, end: 9 }); }
}
```

Run `cargo test -p hongguo-desktop range` → FAIL (`todo!`).

- [ ] **Step 2: Implement `parse_range`**

```rust
pub fn parse_range(header: Option<&str>, len: u64) -> RangeResult {
    let Some(spec) = header.and_then(|h| h.trim().strip_prefix("bytes=")) else { return RangeResult::Full };
    let first = spec.split(',').next().unwrap_or("").trim();
    let Some((a, b)) = first.split_once('-') else { return RangeResult::Full };
    if len == 0 { return RangeResult::Unsatisfiable; }
    let (start, end) = match (a.trim(), b.trim()) {
        ("", n) => match n.parse::<u64>() { Ok(0) | Err(_) => return RangeResult::Unsatisfiable,
                                            Ok(n) => (len.saturating_sub(n), len - 1) },
        (s, "") => match s.parse::<u64>() { Ok(s) => (s, len - 1), Err(_) => return RangeResult::Full },
        (s, e) => match (s.parse::<u64>(), e.parse::<u64>()) {
            (Ok(s), Ok(e)) if s <= e => (s, e.min(len - 1)),
            _ => return RangeResult::Full,
        },
    };
    if start >= len { RangeResult::Unsatisfiable } else { RangeResult::Partial { start, end } }
}
```

Re-run → PASS.

- [ ] **Step 3: Tauri shell.** `src-tauri/Cargo.toml` package name `hongguo-desktop`, deps `tauri = "2"`, `tauri-build = "2"` (build), `tokio`. Register `.register_asynchronous_uri_scheme_protocol("media", ...)` in `lib.rs`; `media_protocol.rs` looks up `media://localhost/<id>` in `Arc<RwLock<HashMap<String, PathBuf>>>`, rejects IDs not matching `^[A-Za-z0-9_-]{1,64}$`, reads only the requested range with `tokio::fs::File` + `seek` + `take` (cap a single response at 4 MiB so memory stays bounded), and sets `Content-Type: video/mp4`, `Accept-Ranges: bytes`, `Content-Range`, `Content-Length`; 416 sets `Content-Range: bytes */<len>`. Follow the Tauri streaming example for the responder pattern.

- [ ] **Step 4: Probe mode.** `--playback-probe` registers every `*_best.mp4` in `$HONGGUO_PROBE_DIR` and loads `ui/index.html?probe=1`; `player.js` in probe mode plays each file, waits for `playing`, checks `videoWidth > 0`, seeks to 0.5 and 0.9 of duration waiting for `seeked`, toggles fullscreen, then reports via `invoke("probe_report", {file, ok, detail})`, which prints `PROBE OK|FAIL <file> <detail>`. Then cycles sources 20 times.

- [ ] **Step 5: Run on this machine** with `GST_DEBUG=2,*decodebin*:4` captured to a log; confirm sound by ear and record decoder, CPU, RSS (`ps -o rss= -C hongguo-desktop,WebKitWebProcess,WebKitNetworkProcess`) in `docs/playback-probe.md`. Also test one H.264 `*.desktop-h264-v1.mp4` file for comparison.

- [ ] **Step 6: Commit** `git commit -m "hongguo: Tauri playback probe with range protocol"`.

**Gate:** If HEVC fails in WebKitGTK, document the exact error (GStreamer log line, `MediaError.code`) and present options to the user before Task 5. Do not carry forward unconditional H.264 re-encoding.

---

### Task 4: Port catalog access and persistent caches

**Goal:** Rust implementations of latest, rank, search, episodes, and video_model return the same results as the legacy backend, with SQLite-backed caches and cover caching.

**Files:**
- Create: `apps/hongguo/crates/hongguo-core/src/{api,catalog,config,cache,images}.rs`
- Create: `apps/hongguo/crates/hongguo-core/tests/{api_contracts,cache,live_api}.rs`
- Create: `apps/hongguo/resources/guest-config.json` (copied from the installed backend; embedded with `include_str!`)

**Acceptance Criteria:**
- [ ] List endpoints (rank, latest) are sent unsigned by default, matching `SIGN_LIST`; search, episodes, and video_model are signed via `hongguo_signer::Sign`.
- [ ] Cache TTLs match the legacy callers (`hongguo.py` call sites: search 10 min, rank 30 min, episodes 6 h, video_model/tracks 5 h) and are stored as versioned JSON rows in SQLite; no pickle reading.
- [ ] HEIC covers are converted to JPEG and cached on disk; non-HEIC images pass through.
- [ ] Unit tests cover malformed JSON, `code != 0`, pagination end, expired cache rows, and request cancellation (dropped future leaves no partial cache row).
- [ ] Expired-session responses surface as `ApiError::SessionExpired` (no `/grab` refresh — the legacy signer never served it).
- [ ] Ignored live test returns the same series IDs as the legacy `/rank?board=recommend&limit=40` and `/search?q=<q>` for the same moment (≥ 90% overlap, ordering may differ).

**Verify:** `cargo test --manifest-path apps/hongguo/Cargo.toml -p hongguo-core` → pass; `cargo test --manifest-path apps/hongguo/Cargo.toml -p hongguo-core --test live_api -- --ignored` with the legacy backend running → pass.

**Steps (re-plan to code level after the gates):**

- [ ] Port query construction, guest config, JSON body serialization, and response parsing from `hongguo.py` (`search`, `get_episodes`, `get_episodes_batch`, `get_video_urls`, `rank`, `latest`) and the throttling in `safeguards.py`.
- [ ] Implement `cache.rs` (rusqlite, table `cache(k TEXT PRIMARY KEY, schema INTEGER, exp INTEGER, v TEXT)`), with bounded retries, Tokio cancellation, and work off the UI thread.
- [ ] Choose the HEIC decoder: `libheif-rs` against system `libheif 1.23` (already installed) is the default; record the package dependency.
- [ ] Commit `hongguo: Rust catalog API and caches`.

**Depends on:** Task 1 for unsigned list endpoints; Task 2 for signed endpoints.

---

### Task 5: Port video preparation and caching

**Goal:** Download, decrypt, and make each episode playable in Rust without Python, ffmpeg, or transcoding (unless Task 3 required it).

**Files:**
- Create: `apps/hongguo/crates/hongguo-core/src/media/{mod,download,mp4,spade,decrypt,select,prepare,cache}.rs`
- Create: `apps/hongguo/crates/hongguo-core/tests/{media_vectors,media_pipeline}.rs`

**Acceptance Criteria:**
- [ ] `spade.rs` reproduces `unwrap_spade.unwrap_v1` for both `flag` values on ≥ 3 captured local vectors; v2 spades return `MediaError::UnsupportedSpade`.
- [ ] Key/flag selection reproduces `offline_decrypt`: try `flag`, then `1-flag`, accept only when the NAL validity check (`oracle.verify_key_iv`) passes.
- [ ] Decryption is AES-128-CTR per sample with each track's own `senc` IV; output decrypts the 5 reference episodes to files whose decoded frames match the legacy `*_best.mp4` (`ffprobe -show_frames` frame count and per-frame `pkt_size` equal — dev check only).
- [ ] Output MP4 has no `sinf`/`senc`/`saio`/`saiz`/`pssh` boxes, sample entries `hvc1`/`mp4a`, and `moov` before `mdat`.
- [ ] `select.rs` reproduces `desktop_quality.choose_desktop_track` (resolution short edge, then size, input order on ties) with table tests: portrait vs landscape (short edge), missing `vwidth`/`vheight` falling back to numeric `definition`, unknown resolution falling back to `size`, equal keys keeping input order, empty input → `None`.
- [ ] Cache writes are atomic (`.partial` + rename), keyed by `(vid, track identity, PREP_VERSION)`; one job per key; total size bounded (default 2 GiB) with LRU eviction that skips files in use.
- [ ] `strace -f -e trace=execve` during preparation of one episode shows no `execve` calls.

**Verify:** `cargo test --manifest-path apps/hongguo/Cargo.toml -p hongguo-core --test media_vectors --test media_pipeline` → pass.

**Steps (re-plan to code level after the gates):**

- [ ] Port `frida/unwrap_spade.py`, `frida/decutil.py` (`senc_iv8`, `decrypt_av`, `tenc_kid`), and `oracle.verify_key_iv` with fixtures from `tests/fixtures/local/media/`.
- [ ] Implement checked MP4 box parsing (all offsets/sizes validated against file length) and a **pure-Rust box rewrite** for CENC stripping and faststart (rename `encv`→original format from `frma`, `enca`→`mp4a`, drop protection boxes, move `moov`, adjust `stco`/`co64`). Add a libav-based path only if Task 3's probe showed this output is insufficient.
- [ ] Next-episode prefetch after parity: one background job, foreground jobs preempt it, cancelled on series change or exit.
- [ ] Commit `hongguo: Rust media preparation`.

**Depends on:** Tasks 3 and 4.

---

### Task 6: Connect the complete interface

**Goal:** The Tauri app delivers the current feeds, search, episode selection, playback, and autoplay using Tauri commands instead of HTTP.

**Files:**
- Modify: `apps/hongguo/ui/index.html`, `ui/player.js`, `ui/styles.css`, `apps/hongguo/src-tauri/src/lib.rs`, `src-tauri/capabilities/main.json`
- Create: `apps/hongguo/ui/api.js`, `ui/app.js`, `apps/hongguo/src-tauri/src/commands.rs`, `src-tauri/src/state.rs`
- Create: `apps/hongguo/tests/player.test.cjs`

**Acceptance Criteria:**
- [ ] `ui/api.js` exports `latest()`, `rank(board)`, `search(q)`, `episodes(seriesId)`, `prepare(seriesId, ep)` (→ `media://localhost/<id>`), `cover(url)`; no `fetch(` to `http://127.0.0.1` remains in `ui/`.
- [ ] All 6 cases from `tests/test_hongguo_player.cjs` are ported to `apps/hongguo/tests/player.test.cjs` and pass, plus new cases: stale result ignored after series change, autoplay rejection shows a play button, preparation failure shows a message with a retry action.
- [ ] Chinese labels and feeds from `scripts/hongguo-web/index.html` are preserved; no remote scripts (`grep -E '<script[^>]+src="https?:' apps/hongguo/ui` → empty).
- [ ] Capabilities allow only the app's own commands and the `media` scheme.
- [ ] Closing the window during preparation exits within 2 s with no leftover `hongguo-desktop` process.

**Verify:** `node --test apps/hongguo/tests/player.test.cjs` → all pass; manual run of `cargo run -p hongguo-desktop` covering manual selection then autoplay, final episode, empty list, rapid series switching, failed preparation, autoplay rejection, and close-during-load.

**Steps (re-plan to code level after the gates):**

- [ ] Port the UI and the autoplay handler; replace `api(path, params)`/`fetch` with `window.__TAURI__.core.invoke` wrappers in `api.js`.
- [ ] Add a generation counter in `app.js` so results from a superseded series/episode request are dropped.
- [ ] Commit `hongguo: complete Tauri interface`.

**Depends on:** Tasks 4 and 5.

---

### Task 7: Package and add a reversible installation path

**Goal:** Install `hongguo-desktop` as an Arch package alongside the legacy app, with a separate desktop entry and data directory, and a scoped removal path.

**Files:**
- Create: `apps/hongguo/packaging/PKGBUILD`, `apps/hongguo/resources/NOTICE`
- Create: `applications/hongguo-rust.desktop`, `scripts/install-hongguo-rust.sh`, `scripts/remove-hongguo-rust.sh`
- Modify: `docs/scripts-guide.md` (new sections + table of contents entries)

**Acceptance Criteria:**
- [ ] `PKGBUILD` builds with `cargo build --release --locked` from a versioned source archive; `depends=()` lists `webkit2gtk-4.1 gstreamer gst-plugins-base gst-plugins-good gst-plugins-bad gst-libav libheif` (adjust only per Task 3/4 records); no `java`, `python`, or browser dependency.
- [ ] `NOTICE` includes licenses for Unicorn, the embedded AOSP bionic libraries (if embedded), and all crate licenses (`cargo about` or `cargo license` output).
- [ ] Data directory is `~/.local/share/hongguo-desktop/`; the install script does not touch `~/.local/bin/launch-hongguo`, `applications/hongguo.desktop`, or `~/.local/share/hongguo-native/`.
- [ ] Optional cache import copies (never moves) validated decrypted `*_best.mp4` files from the legacy `stream-cache`; failure falls back to refetching.
- [ ] `remove-hongguo-rust.sh` removes only the package, its desktop entry, and (with `--purge`) `~/.local/share/hongguo-desktop/`.

**Verify:** `cd apps/hongguo/packaging && makepkg --cleanbuild` → package built; `namcap *.pkg.tar.zst` → no errors; install, launch, remove, then `ls ~/.local/bin/launch-hongguo ~/.local/share/hongguo-native/backend/server.py` → both still exist.

**Steps (re-plan to code level after the gates):**

- [ ] Write PKGBUILD, desktop entry, install/remove scripts (follow `scripts/install-hongguo.sh` conventions and `hongguo-common.sh` helpers where reusable).
- [ ] Document install, diagnostics, dependencies, and rollback in `docs/scripts-guide.md`.
- [ ] Commit `hongguo: package and install scripts`.

**Depends on:** Task 6.

---

### Task 8: Verify parity and performance before switching defaults (GATE)

**Goal:** Demonstrate in an isolated runtime that the packaged app needs no Python, JVM, or browser, matches legacy features, and meets or beats the Task 1 baseline, then present results before any default switch.

> **USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

**Files:**
- Create: `apps/hongguo/tests/desktop-smoke.mjs`, `apps/hongguo/tools/verify-runtime.sh`, `apps/hongguo/docs/acceptance.md`

**Acceptance Criteria:**
- [ ] `cargo fmt --check`, `cargo clippy -D warnings`, `cargo test --workspace --locked`, and `node --test tests/player.test.cjs` all exit 0.
- [ ] `desktop-smoke.mjs` (WebdriverIO via `tauri-driver` + `WebKitWebDriver`) exercises browse → search → select → play → seek → autoplay → final episode → exit, and the API-failure and cancelled-preparation paths.
- [ ] `verify-runtime.sh target/release/hongguo-desktop` runs the app under `bwrap` with `/usr/lib/jvm`, `/usr/bin/python*`, `~/.local/share/hongguo-native`, and browser binaries masked, records `strace -f -e trace=execve` and `ldd`, and fails if any `execve` other than the app and `WebKit*Process` appears.
- [ ] `docs/acceptance.md` repeats every Task 1 measurement with the same episodes, cache state, and sample count, shows the delta, and flags each regression explicitly; next-episode transition delay is lower than baseline.
- [ ] Live signing and API ignored tests pass and their output is pasted into `docs/acceptance.md`.
- [ ] Results are presented to the user; the default launcher is unchanged at task close.

**Verify:** from `apps/hongguo/`:
```bash
cargo fmt --all -- --check
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --locked
node --test tests/player.test.cjs
cargo install tauri-driver --locked   # WebKitWebDriver: confirm package source before installing
node tests/desktop-smoke.mjs
./tools/verify-runtime.sh target/release/hongguo-desktop
cargo test --workspace -- --ignored
```
All exit 0; `docs/acceptance.md` contains the measurement table and real-playback observations.

**Steps (re-plan to code level after the gates):**

- [ ] Find which Arch package ships `WebKitWebDriver` (`pacman -F WebKitWebDriver`; not present in `webkit2gtk-4.1 2.54.2` file list) and record it as a dev-only dependency.
- [ ] Write the smoke test, the runtime verifier, and the acceptance report.
- [ ] Commit `hongguo: acceptance verification` and stop for user review.

**Depends on:** Task 7.

## Review milestone

The first milestone is Tasks 2 and 3: an in-process Rust signer accepted by the live service and a Tauri probe playing the HEVC episodes. They decide whether the full replacement is practical. The legacy native client stays available throughout.
