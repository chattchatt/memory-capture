# 001 — Three-stage design (enqueue → background extract → confirm & apply)

Date: 2026-10-05

## Why not extract inside SessionEnd
Claude Code SessionEnd hooks share a ~1.5 s timeout and cannot block; work that must outlive the
CLI is not guaranteed. Extraction calls a model and takes tens of seconds, so SessionEnd only
appends a small pending record.

## Why a launchd watcher
The pending folder is watched (macOS `WatchPaths`); the worker runs `claude -p --bare` per item and
writes a candidates file. `--bare` skips hooks/skills, and `MEMORY_CAPTURE_CHILD=1` makes our own
hooks no-op as a second guard against recursion.

## Why writes are done by code, not the model
Placement rules (which layer, which folder index, pointer vs body) must be identical every time and
testable. The model only proposes; `apply` writes deterministically and refuses unsafe input
(bad names, overwrites, phone-number-like strings).

## Layout model
- `kernel_dir` (optional): shared store for feedback/project bodies + `INDEX.md`.
- Per-folder Claude memory `~/.claude/projects/<slug>/memory/MEMORY.md`: pointers for that folder.
- Home memory: things that belong to no folder.
Without `kernel_dir`, bodies live directly in the folder/home memory dir.
