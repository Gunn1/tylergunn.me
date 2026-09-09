#!/usr/bin/env python3
"""
Capture notes while you work, then turn them into a writeup draft.

The problem this solves: the interesting part of a writeup is the dead ends,
and those are exactly what you forget by the time you sit down to write. So
record them as they happen, in one keystroke, and assemble later.

    ./writeup.py start heap-overflow "Plaid pwn 300"
    ./writeup.py note "len is int32, negative passes the check"
    ./writeup.py note --fail "tried mmap at 0 - mmap_min_addr is 65536"
    ./writeup.py code exploit.py:40-58
    ./writeup.py run checksec ./chal
    ./writeup.py note --win "fake vtable on _IO_2_1_stdout_"
    ./writeup.py build

`build` writes content/writeups/<date>-<slug>.md as a draft, in the same
section shape as the existing posts, ready for `python3 build.py --dev`.

Sessions live in .writeup/ (gitignored) — they are working notes, not output.
Standard library only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SESSIONS = ROOT / ".writeup"
CURRENT = SESSIONS / "current"
DRAFTS = ROOT / "content" / "writeups"

# Note kind -> the section it lands in. Order here is section order in the
# finished draft.
SECTIONS: dict[str, str] = {
    "note": "What I tried",
    "fail": "Dead ends",
    "win": "What worked",
    "takeaway": "Takeaways",
}

LANGS = {
    ".py": "python", ".js": "javascript", ".ts": "typescript", ".c": "c",
    ".h": "c", ".cpp": "cpp", ".rs": "rust", ".go": "go", ".sh": "bash",
    ".rb": "ruby", ".php": "php", ".java": "java", ".sql": "sql",
    ".html": "html", ".css": "css", ".json": "json", ".toml": "toml",
    ".yml": "yaml", ".yaml": "yaml", ".md": "markdown", ".asm": "nasm",
}


class WriteupError(Exception):
    pass


@dataclass
class Entry:
    kind: str  # note | fail | win | takeaway | code | run
    text: str
    at: str
    lang: str = ""
    caption: str = ""


@dataclass
class Session:
    slug: str
    title: str
    started: str
    tags: str = "ctf"
    entries: list[Entry] = field(default_factory=list)

    @property
    def path(self) -> Path:
        return SESSIONS / f"{self.slug}.json"

    def save(self) -> None:
        SESSIONS.mkdir(exist_ok=True)
        payload = asdict(self)
        self.path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, slug: str) -> Session:
        path = SESSIONS / f"{slug}.json"
        if not path.exists():
            raise WriteupError(f"no session {slug!r} — start one with: writeup start {slug}")
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["entries"] = [Entry(**e) for e in raw.get("entries", [])]
        return cls(**raw)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", text) or "untitled"


def now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def set_current(slug: str | None) -> None:
    SESSIONS.mkdir(exist_ok=True)
    if slug is None:
        CURRENT.unlink(missing_ok=True)
    else:
        CURRENT.write_text(slug, encoding="utf-8")


def get_current() -> str:
    if not CURRENT.exists():
        raise WriteupError("no active session — start one with: writeup start <slug>")
    return CURRENT.read_text(encoding="utf-8").strip()


def resolve(slug: str | None) -> Session:
    return Session.load(slug or get_current())


def add(session: Session, entry: Entry, label: str) -> None:
    session.entries.append(entry)
    session.save()
    print(f"  {label}  ({len(session.entries)} entries in {session.slug})")


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


def cmd_start(args) -> None:
    slug = slugify(args.slug)
    path = SESSIONS / f"{slug}.json"

    if path.exists() and not args.force:
        set_current(slug)
        session = Session.load(slug)
        print(f"  resumed {slug} ({len(session.entries)} entries)")
        return

    session = Session(
        slug=slug, title=args.title or args.slug, started=now(), tags=args.tags
    )
    session.save()
    set_current(slug)
    print(f"  started {slug}")
    print("  add notes with: writeup note \"...\"  ·  --fail  ·  --win  ·  --takeaway")


def cmd_note(args) -> None:
    text = " ".join(args.text).strip() or sys.stdin.read().strip()
    if not text:
        raise WriteupError("nothing to record — pass text or pipe it in")

    kind = "fail" if args.fail else "win" if args.win else "takeaway" if args.takeaway else "note"
    session = resolve(args.session)
    add(session, Entry(kind=kind, text=text, at=now()), SECTIONS[kind].lower())


def cmd_code(args) -> None:
    spec = args.path
    lines_part = ""
    if ":" in spec and not Path(spec).exists():
        spec, lines_part = spec.rsplit(":", 1)

    path = Path(spec)
    if not path.exists():
        raise WriteupError(f"no such file: {path}")

    body = path.read_text(encoding="utf-8", errors="replace").splitlines()
    caption = args.caption or path.name

    if lines_part:
        m = re.fullmatch(r"(\d+)(?:-(\d+))?", lines_part)
        if not m:
            raise WriteupError(f"bad line range {lines_part!r} — use file.py:40 or file.py:40-58")
        start = int(m.group(1))
        end = int(m.group(2) or start)
        if start < 1 or start > len(body):
            raise WriteupError(f"{path} has {len(body)} lines; {start} is out of range")
        body = body[start - 1 : end]
        caption = f"{path.name}:{lines_part}"

    session = resolve(args.session)
    add(
        session,
        Entry(
            kind="code",
            text="\n".join(body).rstrip(),
            at=now(),
            lang=args.lang or LANGS.get(path.suffix, ""),
            caption=caption,
        ),
        f"code from {caption}",
    )


def cmd_run(args) -> None:
    if not args.command:
        raise WriteupError("nothing to run")

    printable = " ".join(args.command)
    print(f"  $ {printable}")

    proc = subprocess.run(args.command, capture_output=True, text=True)
    output = (proc.stdout + proc.stderr).rstrip()
    if output:
        print(output)

    # Keep the transcript in the shape it will appear in the writeup.
    transcript = f"$ {printable}"
    if output:
        transcript += "\n" + output

    session = resolve(args.session)
    add(session, Entry(kind="code", text=transcript, at=now(), lang="", caption=""),
        f"captured `{printable}`")

    if proc.returncode:
        print(f"  (exit {proc.returncode} — recorded anyway)")


def cmd_status(args) -> None:
    session = resolve(args.session)
    started = session.started.replace("T", " ")
    print(f"\n  {session.slug} — {session.title}")
    print(f"  started {started} · {len(session.entries)} entries\n")

    if not session.entries:
        print("  (nothing recorded yet)\n")
        return

    marks = {"note": "·", "fail": "✗", "win": "✓", "takeaway": "»", "code": "▸"}
    for e in session.entries:
        stamp = e.at.split("T")[1]
        if e.kind == "code":
            first = e.text.splitlines()[0] if e.text else ""
            label = e.caption or first[:48]
            n = len(e.text.splitlines())
            print(f"  {stamp}  {marks['code']} {label}  ({n} lines)")
        else:
            print(f"  {stamp}  {marks[e.kind]} {e.text}")
    print()


def cmd_list(args) -> None:
    SESSIONS.mkdir(exist_ok=True)
    files = sorted(SESSIONS.glob("*.json"))
    if not files:
        print("  no sessions yet")
        return

    active = CURRENT.read_text(encoding="utf-8").strip() if CURRENT.exists() else ""
    print()
    for f in files:
        s = Session.load(f.stem)
        mark = "*" if s.slug == active else " "
        print(f"  {mark} {s.slug:<28} {len(s.entries):>3} entries   {s.started.split('T')[0]}")
    print("\n  * = active\n")


def cmd_drop(args) -> None:
    session = resolve(args.session)
    if not args.yes:
        raise WriteupError(f"this deletes {session.path.name} — re-run with --yes to confirm")
    session.path.unlink()
    if CURRENT.exists() and CURRENT.read_text(encoding="utf-8").strip() == session.slug:
        set_current(None)
    print(f"  dropped {session.slug}")


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------


def render(session: Session) -> str:
    date = session.started.split("T")[0]

    # Walk entries in order, filing each into a section. A code block belongs
    # to whichever section the note before it opened, so a snippet recorded
    # right after a --fail lands under Dead ends.
    buckets: dict[str, list[str]] = {name: [] for name in SECTIONS.values()}
    current = SECTIONS["note"]

    for e in session.entries:
        if e.kind == "code":
            fence = f"```{e.lang}\n{e.text}\n```"
            if e.caption:
                fence = f"*{e.caption}*\n\n{fence}"
            buckets[current].append(fence)
        else:
            current = SECTIONS[e.kind]
            buckets[current].append(f"- {e.text}")

    parts = [
        "---",
        f"title: {session.title}",
        f"slug: {session.slug}",
        f"date: {date}",
        "description: One sentence for the index and the feed.",
        f"tags: {session.tags}",
        "draft: true",
        "---",
        "",
        "<!-- Recorded with writeup.py. Notes are raw — rewrite them into prose. -->",
        "",
        "Set the scene in a paragraph: what the target was, why you were looking at it.",
        "",
    ]

    for name in SECTIONS.values():
        items = buckets[name]
        if not items:
            continue
        parts.append(f"## {name}")
        parts.append("")
        parts.extend(_join_items(items))
        parts.append("")

    return "\n".join(parts).rstrip() + "\n"


def _join_items(items: list[str]) -> list[str]:
    """Bullets pack together; code blocks get blank lines around them."""
    out: list[str] = []
    for i, item in enumerate(items):
        is_block = item.startswith("```") or item.startswith("*")
        if is_block and out and out[-1] != "":
            out.append("")
        out.append(item)
        if is_block and i != len(items) - 1:
            out.append("")
    return out


def cmd_build(args) -> None:
    session = resolve(args.session)
    if not session.entries:
        raise WriteupError(f"{session.slug} has no entries yet — nothing to build")

    if args.title:
        session.title = args.title
    if args.tags:
        session.tags = args.tags
    if args.title or args.tags:
        session.save()

    date = session.started.split("T")[0]
    target = DRAFTS / f"{date}-{session.slug}.md"

    if target.exists() and not args.force:
        raise WriteupError(f"{target.relative_to(ROOT)} already exists — re-run with --force")

    DRAFTS.mkdir(parents=True, exist_ok=True)
    if target.exists():
        backup = target.with_suffix(".md.bak")
        shutil.copy2(target, backup)
        print(f"  backed up existing draft to {backup.name}")

    target.write_text(render(session), encoding="utf-8")

    counts: dict[str, int] = {}
    for e in session.entries:
        counts[e.kind] = counts.get(e.kind, 0) + 1
    summary = ", ".join(f"{n} {k}" for k, n in sorted(counts.items()))

    print(f"\n  wrote {target.relative_to(ROOT)}")
    print(f"  from {len(session.entries)} entries ({summary})")
    print("\n  It is marked draft: true — it will not publish until you remove that.")
    print("  Preview it with: python3 build.py --dev\n")


# ---------------------------------------------------------------------------
# cli
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="writeup",
        description="Record notes while you work; assemble a writeup draft afterwards.",
    )
    # -s lives on each subcommand rather than the top level, so it reads the
    # way people actually type it: `writeup drop -s foo`, not `writeup -s foo drop`.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "-s", "--session", help="act on this session instead of the active one"
    )

    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("start", help="start or resume a session")
    p.add_argument("slug")
    p.add_argument("title", nargs="?", help="human title; defaults to the slug")
    p.add_argument("--tags", default="ctf", help="comma-separated tags for the draft")
    p.add_argument("--force", action="store_true", help="restart even if it exists")
    p.set_defaults(fn=cmd_start)

    p = sub.add_parser("note", help="record a note", parents=[common])
    p.add_argument("text", nargs="*")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--fail", action="store_true", help="file under Dead ends")
    g.add_argument("--win", action="store_true", help="file under What worked")
    g.add_argument("--takeaway", action="store_true", help="file under Takeaways")
    p.set_defaults(fn=cmd_note)

    p = sub.add_parser("code", help="capture a file or line range", parents=[common])
    p.add_argument("path", help="path, optionally file.py:40 or file.py:40-58")
    p.add_argument("--lang", help="override the fence language")
    p.add_argument("--caption", help="override the caption")
    p.set_defaults(fn=cmd_code)

    p = sub.add_parser("run", help="run a command and capture it with its output", parents=[common])
    p.add_argument("command", nargs=argparse.REMAINDER)
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("status", help="show what has been recorded", parents=[common])
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("list", help="list all sessions")
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("drop", help="delete a session", parents=[common])
    p.add_argument("--yes", action="store_true")
    p.set_defaults(fn=cmd_drop)

    p = sub.add_parser("build", help="write the draft into content/writeups/", parents=[common])
    p.add_argument("--title", help="set the title as you build")
    p.add_argument("--tags", help="set the tags as you build")
    p.add_argument("--force", action="store_true", help="overwrite an existing draft")
    p.set_defaults(fn=cmd_build)

    args = ap.parse_args()

    try:
        args.fn(args)
    except WriteupError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
