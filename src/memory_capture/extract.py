"""Ask a headless Claude for memory candidates."""

from __future__ import annotations

import json
import os
import re
import subprocess

from .config import SCOPES, TYPES


class ExtractionError(Exception):
    pass


PROMPT = """You review one finished Claude Code session and propose durable memories for future sessions.

Rules:
- Propose at most {max_n} candidates; propose none if nothing is worth keeping. Most sessions have 0-2.
- Keep only what will change how future work is done: the user's feedback or preferences (type
  "feedback"), the current state/decisions of ongoing work (type "project"), facts about the user
  (type "user"), or pointers to people, tools, accounts, procedures (type "reference").
- Skip: summaries of the conversation, anything already recorded in code/commits/files, things only
  needed in this session, credentials, financial data, phone numbers, customers' raw personal data.
- scope "folder" if it only matters when working in the session folder ({cwd}); otherwise "home".
- name: lowercase snake_case prefixed by the type, e.g. feedback_reports_as_tables.
- If the session's working folder already has a memory on the same topic (see existing list), set
  "update_existing" to that name and put only the new part in body.
- body: the fact first; for feedback/project add lines "**Why:** ..." and "**How to apply:** ...".
- Write title/summary/body in the language the user used.
{extra_rules}
Existing memories in this folder (name — summary):
{existing}

Return ONLY JSON: {{"candidates": [{{"name": "...", "type": "...", "scope": "...", "title": "...",
"summary": "one line", "body": "...", "update_existing": null}}]}}

Session dialogue:
{dialogue}
"""


def build_prompt(dialogue: str, context: dict, max_n: int, extra_rules: str = "") -> str:
    return PROMPT.format(max_n=max_n, cwd=context.get("cwd", ""), extra_rules=extra_rules,
                         existing=context.get("existing", "(none)"), dialogue=dialogue)


def parse_candidates(text: str) -> list[dict]:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ExtractionError("no JSON object in model output")
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise ExtractionError(f"bad JSON: {e}") from e
    cands = data.get("candidates") if isinstance(data, dict) else None
    if not isinstance(cands, list):
        raise ExtractionError("missing 'candidates' list")
    return cands


NAME = re.compile(r"^[a-z][a-z0-9_]{2,80}$")


def valid(c: dict) -> bool:
    return (isinstance(c, dict) and isinstance(c.get("name"), str) and bool(NAME.match(c["name"]))
            and c.get("type") in TYPES and c.get("scope") in SCOPES
            and all(isinstance(c.get(k), str) and c.get(k).strip() for k in ("title", "summary", "body"))
            and (c.get("update_existing") in (None, "") or bool(NAME.match(str(c["update_existing"])))))


class ClaudeCliExtractor:
    """Runs `claude -p` as a child with all hooks disabled (`--settings {"disableAllHooks": true}`).

    `--bare` would also skip hooks but it skips OAuth login too, so subscription users could not
    use it. The env guard is a second line of defense for our own hooks.
    """

    def __init__(self, claude_bin="claude", timeout_s=300, max_n=5, extra_rules="",
                 run=subprocess.run, base_env=None, model=None, cwd=None):
        self.claude_bin, self.timeout_s, self.max_n, self.extra_rules = claude_bin, timeout_s, max_n, extra_rules
        self.model, self.cwd = model, cwd
        self.run = run
        self.base_env = dict(os.environ) if base_env is None else base_env

    def extract(self, dialogue: str, context: dict) -> list[dict]:
        prompt = build_prompt(dialogue, context, self.max_n, self.extra_rules)
        env = dict(self.base_env, MEMORY_CAPTURE_CHILD="1")
        args = [self.claude_bin, "-p", "--settings", '{"disableAllHooks": true}', "--output-format", "json"]
        if self.model:
            args += ["--model", self.model]
        try:
            proc = self.run(args, input=prompt, capture_output=True, text=True,
                            timeout=self.timeout_s, env=env, cwd=self.cwd)
        except subprocess.TimeoutExpired as e:
            raise ExtractionError("timeout") from e
        except OSError as e:
            raise ExtractionError(f"cannot run {self.claude_bin}: {e}") from e
        if proc.returncode != 0:
            raise ExtractionError(f"exit {proc.returncode}: {(proc.stderr or '')[:300]}")
        try:
            result = json.loads(proc.stdout).get("result", "")
        except (json.JSONDecodeError, AttributeError):
            result = proc.stdout
        return parse_candidates(result)
