"""Write accepted candidates. Placement is decided here by code, never by the model."""

from __future__ import annotations

import re
from pathlib import Path

from .config import Config
from .extract import valid
from .inbox import Inbox
from .layout import folder_memory_dir, home_memory_dir

PHONE = re.compile(r"(?<![0-9])01[0-9]-?\d{3,4}-?\d{4}(?![0-9])")


class ApplyError(Exception):
    pass


def _frontmatter(c: dict) -> str:
    return f"---\nname: {c['name']}\ndescription: {c['summary']}\nmetadata:\n  type: {c['type']}\n---\n\n"


def _index_header(mem_dir: Path, cfg: Config) -> str:
    lines = [f"# {mem_dir.parent.name} memory index", ""]
    if cfg.kernel_dir:
        lines.append(f"- Shared rules and feedback first: `{cfg.kernel_dir / 'INDEX.md'}`")
    else:
        lines.append("- Shared rules and feedback: home memory index")
    return "\n".join(lines) + "\n\n"


def _add_index_line(index: Path, line: str, header: str = "") -> None:
    index.parent.mkdir(parents=True, exist_ok=True)
    text = index.read_text() if index.exists() else header
    if line.split("](")[1].split(")")[0] in text:
        return
    index.write_text(text.rstrip("\n") + "\n" + line + "\n")


def _line(c: dict) -> str:
    return f"- [{c['title']}]({c['name']}.md) — {c['summary']}"


def _plan(cfg: Config, c: dict, cwd: str, git_root) -> dict:
    target_dir = folder_memory_dir(cfg, cwd, git_root) if c["scope"] == "folder" else home_memory_dir(cfg)
    in_kernel = bool(cfg.kernel_dir) and c["type"] in ("feedback", "project")
    body_dir = cfg.kernel_dir if in_kernel else target_dir
    return {"target_dir": target_dir, "in_kernel": in_kernel, "body_path": body_dir / f"{c['name']}.md"}


def _check(cfg: Config, c: dict, cwd: str, git_root) -> dict:
    if not valid(c):
        raise ApplyError(f"invalid candidate: {c.get('name')!r}")
    blob = " ".join(str(c.get(k, "")) for k in ("title", "summary", "body"))
    if PHONE.search(blob):
        raise ApplyError(f"{c['name']}: contains a phone-number-like string; edit it out first")
    plan = _plan(cfg, c, cwd, git_root)
    upd = c.get("update_existing")
    if upd:
        plan["body_path"] = plan["body_path"].with_name(f"{upd}.md")
        if not plan["body_path"].exists():
            raise ApplyError(f"{c['name']}: update target {plan['body_path']} does not exist")
    elif plan["body_path"].exists():
        raise ApplyError(f"{c['name']}: {plan['body_path']} already exists (set update_existing)")
    return plan


def _write(cfg: Config, c: dict, plan: dict, clock) -> str:
    body_path: Path = plan["body_path"]
    if c.get("update_existing"):
        with open(body_path, "a", encoding="utf-8") as f:
            f.write(f"\n\n## Update {clock.today()}\n{c['body'].strip()}\n")
        return f"updated {body_path}"
    body_path.parent.mkdir(parents=True, exist_ok=True)
    body_path.write_text(_frontmatter(c) + c["body"].strip() + "\n")
    tdir: Path = plan["target_dir"]
    header = _index_header(tdir, cfg)
    if plan["in_kernel"]:
        _add_index_line(cfg.kernel_dir / "INDEX.md", _line(c))
        ptr = tdir / f"{c['name']}.md"
        tdir.mkdir(parents=True, exist_ok=True)
        ptr.write_text(_frontmatter(dict(c, summary=c["summary"] + " (pointer)")) + f"Body: `{body_path}`\n")
    _add_index_line(tdir / "MEMORY.md", _line(c), header)
    return f"wrote {body_path}"


def apply_candidates(cfg: Config, session_id: str, accept: list[int], git_root, clock) -> list[str]:
    inbox = Inbox(cfg.inbox_dir)
    data = inbox.get_candidates(session_id)
    if not data:
        raise ApplyError(f"no candidates for session {session_id}")
    cands = data.get("candidates", [])
    if any(n < 1 or n > len(cands) for n in accept):
        raise ApplyError(f"numbers must be between 1 and {len(cands)}")
    cwd = data.get("cwd") or str(cfg.home_dir)
    chosen = [cands[n - 1] for n in accept]
    plans = [_check(cfg, c, cwd, git_root) for c in chosen]  # validate all before writing any
    results = [_write(cfg, c, p, clock) for c, p in zip(chosen, plans)]
    inbox.close_candidates(session_id, dict(data, accepted=accept, applied_at=clock.now_iso(), results=results))
    return results


def discard(cfg: Config, session_id: str, clock) -> None:
    inbox = Inbox(cfg.inbox_dir)
    data = inbox.get_candidates(session_id)
    if not data:
        raise ApplyError(f"no candidates for session {session_id}")
    inbox.close_candidates(session_id, dict(data, accepted=[], applied_at=clock.now_iso()))
