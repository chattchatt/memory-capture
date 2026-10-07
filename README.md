# memory-capture

Claude Code forgets what you taught it unless you remember to say "save this". `memory-capture`
collects memory candidates automatically when a session ends (`/clear` or exit), and asks you to
confirm them at the start of your next session. Nothing is saved without your yes.

## How it works

```
/clear or exit ──► SessionEnd hook ──► inbox/pending/<session>.json        (fast, < 1.5 s budget)
                                             │  launchd WatchPaths
                                             ▼
                                   memory-capture work
                       claude -p, hooks disabled  (reads the transcript, proposes ≤ 5 candidates)
                                             │
                                             ▼
next session ──► SessionStart hook ──► "N memory candidates are waiting" injected as context
                                             │  you pick numbers
                                             ▼
                    memory-capture apply <session> --accept 1,3   (writes by fixed rules)
```

- **Placement is done by code, not by the model.** `feedback`/`project` bodies go to your shared
  store (`kernel_dir`) with a pointer in the folder's memory index; `user`/`reference` go to the
  folder or home memory. Without `kernel_dir`, bodies live in Claude Code's per-folder memory.
- **Per-folder memory.** Candidates scoped to a folder land in
  `~/.claude/projects/<folder-slug>/memory/MEMORY.md`, the file Claude Code loads when you open a
  session in that folder (git root decides the folder).
- **Killed windows and failures.** SessionEnd does not fire when a terminal is killed or Claude Code
  crashes. At each session start a sweep queues interactive transcripts that have been idle for
  `sweep_idle_minutes` (default 120) within the last `sweep_lookback_days` and were never taken, or
  have grown since (a ledger `done.json` keeps the size last extracted). Failed extractions are
  retried after `retry_after_hours`, up to `max_retry_rounds` times. Only one worker runs at a time.
- **Safety.** No overwrite of existing memories (updates append a dated section), names are
  validated, and anything that looks like a phone number is refused. The extraction child runs with
  all hooks disabled (`disableAllHooks`) and an env guard so it never re-triggers them.

## Install (macOS)

```bash
git clone https://github.com/chattchatt/memory-capture && cd memory-capture
python3 -m venv .venv && .venv/bin/pip install -e .
mkdir -p ~/.config/memory-capture && cp contrib/config.example.toml ~/.config/memory-capture/config.toml
.venv/bin/memory-capture install --exe "$PWD/.venv/bin/memory-capture"
```

`install` prints two snippets: the hook entries to **add** to `~/.claude/settings.json` (keep your
existing hooks) and a launchd plist that runs the worker whenever a session is queued.

## Commands

Global options such as `--config <file>` go before the subcommand: `memory-capture --config c.toml show`.
If a multi-item `apply` fails midway, fix the cause and re-run the same command; items already saved are skipped.

| command | what it does |
|---|---|
| `memory-capture show` | list waiting candidates, numbered |
| `memory-capture apply <session> --accept 1,3` | save the accepted ones |
| `memory-capture discard <session>` | drop a session's candidates |
| `memory-capture status` | pending / candidates / failed counts |
| `memory-capture work` | run extraction now (launchd does this for you) |
| `memory-capture sweep [--dry-run]` | queue sessions that ended without SessionEnd (session start does this for you) |
| `memory-capture retry` | move every failed session back to pending now |

First time you upgrade to a version with the sweep, run `memory-capture sweep --dry-run` before
opening a new session: everything idle in the last week that was never taken would be queued at once.

## Development

```bash
make check     # syntax + pytest; every external dependency is a seam with a test double
make smoke     # runs the real `claude -p` once on a fake dialogue, prints OK/FAIL (not in check; needs login)
```

Seams: transcript reader (real JSONL schema fixture), extractor (`subprocess.run` double), inbox
root (temp dir), clock (fixed), git-root resolver (mapping). See `goals/` and `decisions/`.

## 한국어 요약

대화를 `/clear`하거나 끝낼 때 기억 후보를 자동으로 모으고, 다음 대화를 시작할 때 확인을 받은 것만
저장합니다. 창을 강제로 닫아 종료 신호가 오지 않은 대화도 다음 대화 시작 때 찾아 모으고, 추출에
실패한 대화는 몇 시간 뒤 다시 시도합니다. 저장 위치(공용 기억 폴더, 작업 폴더별 기억 목록, 홈 기억)는 모델이 아니라 코드가 정해진
규칙대로 정합니다.

License: MIT
