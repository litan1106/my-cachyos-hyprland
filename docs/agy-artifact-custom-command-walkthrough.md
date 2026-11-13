# Antigravity CLI Customizations — Walkthrough

[Documentation index](README.md)

This is a historical record of machine-local configuration. The plugin and status line implementations are not shipped in this repository.

## What was created

Two customizations for the Antigravity CLI:

1. **`artifact-manager` plugin** — 6 slash commands for artifact management
2. **Custom status line** — Dynamic, color-coded status bar (~7ms render)

---

## 1. Artifact Manager Plugin

### Location
```
~/.gemini/antigravity-cli/plugins/artifact-manager/
├── plugin.json                    # Plugin manifest
└── skills/
    ├── list/SKILL.md              → /artifact-manager:list
    ├── open/SKILL.md              → /artifact-manager:open
    ├── export/SKILL.md            → /artifact-manager:export
    ├── search/SKILL.md            → /artifact-manager:search
    ├── recent/SKILL.md            → /artifact-manager:recent
    └── copy/SKILL.md              → /artifact-manager:copy
```

### Slash Commands

| Command | Purpose |
|---------|---------|
| `/artifact-manager:list` | List artifacts in current or all conversations |
| `/artifact-manager:open` | Open an artifact in `$EDITOR` |
| `/artifact-manager:export` | Bulk export artifacts to a directory |
| `/artifact-manager:search` | Search artifact contents by keyword |
| `/artifact-manager:recent` | Show most recently modified artifacts |
| `/artifact-manager:copy` | Quick-copy a single artifact to a path or clipboard |

### Activation
Restart `agy` → verify with `agy plugin list`

---

## 2. Custom Status Line

### Files Modified/Created

| File | Change |
|------|--------|
| `~/.gemini/antigravity-cli/statusline.sh` | **[NEW]** Optimized status line script |
| `~/.gemini/antigravity-cli/settings.json` | **[MODIFIED]** Added `statusLine` config block |

### What the status line shows

```
 ⚡ WORK  │ Opus 4.6⚡ │  main* │ ████░░░░░░ 42% 88k↑61k↓ │ 📄2 │ 🤖1 │ cde317dc
```

| Segment | Description |
|---------|-------------|
| `⚡ WORK` | Agent state badge (idle/thinking/working/tool/init) — color-coded |
| `Opus 4.6⚡` | Model name (auto-shortened) |
| ` main*` | Git branch + dirty indicator (`*`) |
| `████░░░░░░ 42%` | Context window usage bar — green→yellow→orange→red |
| `88k↑61k↓` | Input/output token counts |
| `📄2` | Artifact count (hidden when 0) |
| `🤖1` | Active subagent count (hidden when 0) |
| `⏳N` | Background task count (hidden when 0) |
| `📨N` | Pending input messages — red badge |
| `⏎` | Tool confirmation pending — yellow badge |
| `🔒` | Sandbox enabled |
| `cde317dc` | Conversation short ID |

### Performance

| Version | Technique | Latency |
|---------|-----------|---------|
| v1 (slow) | 3× python3 spawns + subshells | ~100-150ms |
| **v2 (current)** | **Single `jq` call + direct `printf`** | **~7ms** |

### Settings.json change

```diff
+  "statusLine": {
+    "type": "command",
+    "command": "~/.gemini/antigravity-cli/statusline.sh"
+  }
```

### Customizing further

Edit `~/.gemini/antigravity-cli/statusline.sh` to add/remove segments, change colors (256-color ANSI), adjust icons, or modify the context bar width. Use `/statusline` to toggle built-in components alongside.
