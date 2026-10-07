# 002 — Sweep at session start for sessions whose SessionEnd never came

Date: 2026-10-07

## Problem
SessionEnd does not fire when a terminal window is killed or Claude Code crashes, so those sessions
were never queued. Separately, extraction failures were final after `max_attempts` tries within an
hour: one evening of failed model calls left seven sessions permanently uncaptured.

## Decision
The SessionStart hook runs a sweep before announcing candidates:
- queue interactive transcripts (`entrypoint` in `interactive_entrypoints`, default `cli`; `claude -p`
  runs are `sdk-cli` and skipped) that are at least `min_transcript_bytes`, idle for
  `sweep_idle_minutes` (default 120), modified within `sweep_lookback_days` (default 7), and not
  already pending, waiting for confirmation or failed;
- a ledger `done.json` keeps the transcript size at the last extraction, so a finished session is
  taken once and a resumed one again only after it grew by `min_transcript_bytes`;
- failures are retried after `retry_after_hours` (default 6), at most `max_retry_rounds` (default 3).

## Why at session start, not on a timer
Session start is when the result is needed (the notice), it already runs our hook, and it adds no new
launchd job. Most files cost one `stat`; only a match reads its head (entrypoint) and last 256 KB (cwd).

## Trade-offs
- A window left open and idle past the threshold is swept while still open. When it really ends it is
  extracted again; the worker then adds new candidate names to the unconfirmed set instead of
  replacing it, so nothing the user has not seen disappears.
- The first sweep after upgrading sees everything idle from the past week. The README tells users to
  run `memory-capture sweep --dry-run` first.
