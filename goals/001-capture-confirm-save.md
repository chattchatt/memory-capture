# Goal 001 — capture at session end, confirm at next start, save by rules

## End state
When a Claude Code session ends by `/clear` or exit, its memory candidates are extracted in the
background and, at the next session start, offered for confirmation. Only confirmed candidates are
written, each to the location its layer/scope rule dictates.

## Proof
- `make check` passes (unit tests use test doubles at every seam: transcript reader, extractor,
  filesystem root, clock, git-root resolver).
- Contract tests: hook stdin fixtures (SessionEnd/SessionStart) and a transcript fixture in the real
  Claude Code JSONL schema parse to the expected records.
- Manual smoke (not in CI): one real `/clear` produces a pending item, the worker produces a
  candidates file, the next session start shows the notice, `memory-capture apply` writes files.

## Must not change
- Existing hooks in `~/.claude/settings.json` (we only add entries).
- SessionEnd hook finishes well under the 1.5 s budget and always exits 0.
- Nothing is written to memory without an explicit `apply`.
- No personal paths or data in the repository (it is public).

## Limits
- At most `max_candidates` (default 5) per session; short sessions are skipped.
- Extraction child runs with `--bare` and an env guard so it never re-triggers the hooks.
