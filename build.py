#!/usr/bin/env python3
"""
Build writeup pages for tylergunn.me.

Reads Markdown from content/writeups/, writes:

    writing/<slug>/index.html     one page per post
    writing/index.html            post list (between the posts markers)
    index.html                    3 most recent (between the posts markers)
    feed.xml                      Atom feed
    sitemap.xml

Standard library only — no pip install, no virtualenv, nothing to keep alive.

Usage:
    python3 build.py              build once
    python3 build.py --serve      build, then serve on :8000
    python3 build.py --watch      rebuild whenever a source file changes
    python3 build.py --new "Title of a new post"
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import html
import http.server
import os
import re
import shutil
import socketserver
import sys
import time
import unicodedata
import xml.sax.saxutils as sx
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "content" / "writeups"
OUT = ROOT / "writing"

SITE_URL = "https://tylergunn.me"
SITE_TITLE = "Tyler Gunn"
AUTHOR = "Tyler Gunn"

# build.py rewrites only what sits between these markers, so the rest of each
# page stays hand-editable.
POSTS_START = "<!-- posts:start -->"
POSTS_END = "<!-- posts:end -->"

HOME_POST_LIMIT = 3


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class Post:
    slug: str
    title: str
    date: dt.date
    description: str
    tags: list[str]
    body_md: str
    draft: bool = False
    source: Path | None = None

    @property
    def url(self) -> str:
        return f"/writing/{self.slug}/"

    @property
    def abs_url(self) -> str:
        return f"{SITE_URL}{self.url}"

    @property
    def iso_date(self) -> str:
        return self.date.isoformat()

    @property
    def rfc3339(self) -> str:
        return f"{self.date.isoformat()}T00:00:00Z"

    @property
    def reading_minutes(self) -> int:
        words = len(re.findall(r"\w+", self.body_md))
        return max(1, round(words / 220))


class BuildError(Exception):
    pass


# ---------------------------------------------------------------------------
# Front matter
# ---------------------------------------------------------------------------


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", text) or "untitled"


def parse_front_matter(raw: str, source: Path) -> tuple[dict[str, str], str]:
    """Split a `---` delimited `key: value` header from the body."""
    if not raw.startswith("---"):
        raise BuildError(f"{source}: missing '---' front matter block")

    parts = raw.split("---", 2)
    if len(parts) < 3:
        raise BuildError(f"{source}: front matter block is not closed")

    meta: dict[str, str] = {}
    for lineno, line in enumerate(parts[1].strip().splitlines(), start=2):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise BuildError(f"{source}:{lineno}: expected 'key: value', got {line!r}")
        key, value = line.split(":", 1)
        meta[key.strip().lower()] = value.strip().strip('"').strip("'")

    return meta, parts[2].strip()


def load_post(path: Path) -> Post:
    meta, body = parse_front_matter(path.read_text(encoding="utf-8"), path)

    missing = {"title", "date"} - meta.keys()
    if missing:
        raise BuildError(f"{path}: missing required key(s): {', '.join(sorted(missing))}")

    try:
        date = dt.date.fromisoformat(meta["date"])
    except ValueError as exc:
        raise BuildError(f"{path}: bad date {meta['date']!r} — use YYYY-MM-DD") from exc

    tags = [t.strip() for t in meta.get("tags", "").split(",") if t.strip()]

    return Post(
        slug=meta.get("slug") or slugify(meta["title"]),
        title=meta["title"],
        date=date,
        description=meta.get("description", ""),
        tags=tags,
        body_md=body,
        draft=meta.get("draft", "").lower() in {"1", "true", "yes"},
        source=path,
    )


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------

# Inline code is pulled out before any other inline rule runs, so its contents
# can never be mangled by the emphasis or link passes.
_PLACEHOLDER = "\x00CODE{}\x00"


def _inline(text: str) -> str:
    stash: list[str] = []

    def stash_code(m: re.Match[str]) -> str:
        stash.append(f"<code>{html.escape(m.group(1), quote=False)}</code>")
        return _PLACEHOLDER.format(len(stash) - 1)

    text = re.sub(r"`([^`]+)`", stash_code, text)
    text = html.escape(text, quote=False)

    # ![alt](src) before [text](href) — the image rule is the more specific one.
    text = re.sub(
        r"!\[([^\]]*)\]\(([^)\s]+)\)",
        lambda m: f'<img src="{html.escape(m.group(2))}" alt="{html.escape(m.group(1))}" loading="lazy">',
        text,
    )
    text = re.sub(
        r"\[([^\]]+)\]\(([^)\s]+)\)",
        lambda m: f'<a href="{html.escape(m.group(2))}"'
        + (' rel="noopener"' if m.group(2).startswith("http") else "")
        + f">{m.group(1)}</a>",
        text,
    )
    text = re.sub(r"&lt;(https?://[^\s&]+)&gt;", r'<a href="\1" rel="noopener">\1</a>', text)

    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", text)
    text = re.sub(r"~~([^~]+)~~", r"<del>\1</del>", text)

    for i, code in enumerate(stash):
        text = text.replace(_PLACEHOLDER.format(i), code)
    return text


def markdown_to_html(md: str) -> str:
    """A deliberately small Markdown subset: what writeups actually need."""
    lines = md.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Fenced code
        if stripped.startswith("```"):
            lang = stripped[3:].strip()
            i += 1
            buf: list[str] = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1  # closing fence
            cls = f' class="language-{html.escape(lang)}"' if lang else ""
            body = html.escape("\n".join(buf), quote=False)
            out.append(f"<pre><code{cls}>{body}</code></pre>")
            continue

        if not stripped:
            i += 1
            continue

        # Horizontal rule
        if re.fullmatch(r"(\*\s*){3,}|(-\s*){3,}|(_\s*){3,}", stripped):
            out.append("<hr>")
            i += 1
            continue

        # Heading
        if m := re.match(r"^(#{1,6})\s+(.*)$", stripped):
            level = len(m.group(1))
            text = _inline(m.group(2).strip())
            anchor = slugify(re.sub(r"<[^>]+>", "", text))
            out.append(f'<h{level} id="{anchor}">{text}</h{level}>')
            i += 1
            continue

        # Blockquote
        if stripped.startswith(">"):
            buf = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append(f"<blockquote>{_inline(' '.join(buf))}</blockquote>")
            continue

        # Table (| a | b | with a |---| separator)
        if stripped.startswith("|") and i + 1 < len(lines) and re.match(
            r"^\|[\s:|-]+\|$", lines[i + 1].strip()
        ):
            header = [c.strip() for c in stripped.strip("|").split("|")]
            i += 2
            rows: list[list[str]] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            thead = "".join(f"<th>{_inline(c)}</th>" for c in header)
            tbody = "".join(
                "<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in rows
            )
            out.append(
                f'<div class="table-wrap"><table><thead><tr>{thead}</tr></thead>'
                f"<tbody>{tbody}</tbody></table></div>"
            )
            continue

        # Lists
        if re.match(r"^[-*+]\s+", stripped) or re.match(r"^\d+[.)]\s+", stripped):
            ordered = bool(re.match(r"^\d+[.)]\s+", stripped))
            pattern = r"^\d+[.)]\s+" if ordered else r"^[-*+]\s+"
            items: list[str] = []
            while i < len(lines) and re.match(pattern, lines[i].strip()):
                items.append(_inline(re.sub(pattern, "", lines[i].strip())))
                i += 1
            tag = "ol" if ordered else "ul"
            body = "".join(f"<li>{it}</li>" for it in items)
            out.append(f"<{tag}>{body}</{tag}>")
            continue

        # Paragraph — consume until a blank line or the start of another block
        buf = []
        while i < len(lines) and lines[i].strip():
            s = lines[i].strip()
            if s.startswith(("```", ">", "|", "#")) or re.match(r"^([-*+]|\d+[.)])\s+", s):
                break
            buf.append(s)
            i += 1
        if buf:
            out.append(f"<p>{_inline(' '.join(buf))}</p>")

    return "\n".join(out)


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

HEADER = """<header class="site-header" id="site-header">
  <div class="wrap site-header__inner">
    <a class="brand" href="/">
      <span class="brand__mark" aria-hidden="true">tg</span>
      <span>tylergunn.me</span>
      <span class="brand__caret" aria-hidden="true">_</span>
    </a>
    <nav class="nav" aria-label="Primary">
      <a class="nav__link" href="/#work">work</a>
      <a class="nav__link" href="/writing/" aria-current="true">writing</a>
      <a class="nav__link" href="/#about">about</a>
      <a class="nav__link" href="/#contact">contact</a>
    </nav>
    <div class="header-actions">
      <button class="term-trigger" id="term-open" type="button" aria-haspopup="dialog">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
             stroke-linecap="round" stroke-linejoin="round" width="15" height="15" aria-hidden="true">
          <polyline points="4 17 10 11 4 5"></polyline>
          <line x1="12" y1="19" x2="20" y2="19"></line>
        </svg>
        <span class="term-trigger__label">terminal</span>
        <span class="term-trigger__key" aria-hidden="true">`</span>
      </button>
      <button class="icon-btn theme-toggle" id="theme-toggle" type="button" aria-label="Toggle colour theme">
        <svg class="icon-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
             stroke-linecap="round" aria-hidden="true">
          <circle cx="12" cy="12" r="4"></circle>
          <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"></path>
        </svg>
        <svg class="icon-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
             stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"></path>
        </svg>
      </button>
    </div>
  </div>
</header>"""

TERMINAL = """<div class="term" id="term" data-open="false" role="dialog" aria-modal="true"
     aria-label="Site terminal" aria-hidden="true">
  <div class="term__window">
    <div class="term__bar">
      <div class="term__dots" aria-hidden="true">
        <span class="term__dot term__dot--close"></span>
        <span class="term__dot term__dot--min"></span>
        <span class="term__dot term__dot--max"></span>
      </div>
      <span class="term__title">tyler@gunn &mdash; bash &mdash; 80&times;24</span>
      <button class="term__close" id="term-close" type="button" aria-label="Close terminal">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"
             stroke-linecap="round" aria-hidden="true">
          <line x1="18" y1="6" x2="6" y2="18"></line>
          <line x1="6" y1="6" x2="18" y2="18"></line>
        </svg>
      </button>
    </div>
    <div class="term__body" id="term-body" tabindex="0" role="log" aria-live="polite"></div>
    <form class="term__prompt-row" id="term-form" autocomplete="off">
      <label class="term__ps1" for="term-input">
        tyler@gunn<span class="d">:</span><span class="path" id="term-path">~</span><span class="d">$</span>
      </label>
      <input class="term__input" id="term-input" name="cmd" type="text"
             placeholder="type 'help' to get started"
             autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false"
             aria-label="Terminal input">
    </form>
    <div class="term__hint">
      <span><kbd>Tab</kbd> complete</span>
      <span><kbd>&uarr;</kbd><kbd>&darr;</kbd> history</span>
      <span><kbd>Ctrl</kbd>+<kbd>L</kbd> clear</span>
      <span><kbd>Esc</kbd> close</span>
    </div>
  </div>
</div>"""

FOOTER = """<footer class="site-footer">
  <div class="wrap site-footer__inner">
    <p>&copy; <span id="year">{year}</span> Tyler Gunn &mdash; built by hand, no frameworks.</p>
    <p>Press <kbd>`</kbd> for a terminal &middot; <a href="/feed.xml">RSS</a></p>
  </div>
</footer>"""

PAGE = """<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} &mdash; Tyler Gunn</title>
<meta name="description" content="{description}">
<link rel="canonical" href="{abs_url}">

<meta property="og:type" content="article">
<meta property="og:url" content="{abs_url}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="article:published_time" content="{iso_date}">
<meta name="twitter:card" content="summary_large_image">

<link rel="icon" href="/assets/img/favicon.svg" type="image/svg+xml">
<link rel="alternate" type="application/atom+xml" title="Tyler Gunn &mdash; Writing" href="/feed.xml">
<meta name="theme-color" content="#08090b" media="(prefers-color-scheme: dark)">
<meta name="theme-color" content="#fcfcfb" media="(prefers-color-scheme: light)">

<link rel="stylesheet" href="/assets/css/style.css">
<link rel="stylesheet" href="/assets/css/terminal.css">
<script src="/assets/js/theme-init.js"></script>

<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"BlogPosting","headline":"{title}",
"datePublished":"{iso_date}","author":{{"@type":"Person","name":"Tyler Gunn",
"url":"https://tylergunn.me"}},"mainEntityOfPage":"{abs_url}"}}
</script>
</head>

<body>
<a class="skip-link" href="#main">Skip to content</a>

{header}

<main id="main" class="section wrap" data-dir="writing">
  <article class="article" data-node="{slug}" data-node-href="{url}">
    <div class="article__head">
      <p class="eyebrow"><span class="sigil">~/</span>writing</p>
      <h1 class="article__title">{title}</h1>
      <div class="article__meta">
        <time datetime="{iso_date}">{iso_date}</time>
        <span>&middot;</span>
        <span>{minutes} min read</span>
        {tags_html}
      </div>
    </div>

    <div class="article__body">
{body}
    </div>

    <div class="article__foot">
      <a class="btn btn--ghost" href="/writing/">&larr; All posts</a>
      <a class="btn btn--ghost" href="/#contact">Get in touch</a>
    </div>
  </article>
</main>

{footer}

{terminal}

<script src="/assets/js/site.js" defer></script>
<script src="/assets/js/terminal.js" defer></script>
</body>
</html>
"""


def render_post_page(post: Post) -> str:
    tags_html = "".join(
        f'<span class="tag">{html.escape(t)}</span>' for t in post.tags
    )
    if tags_html:
        tags_html = f'<span class="post__tags" style="margin:0">{tags_html}</span>'

    return PAGE.format(
        title=html.escape(post.title),
        description=html.escape(post.description or post.title),
        abs_url=post.abs_url,
        url=post.url,
        slug=html.escape(post.slug),
        iso_date=post.iso_date,
        minutes=post.reading_minutes,
        tags_html=tags_html,
        body=markdown_to_html(post.body_md),
        header=HEADER,
        footer=FOOTER.format(year=dt.date.today().year),
        terminal=TERMINAL,
    )


def render_post_list(posts: list[Post]) -> str:
    items = []
    for p in posts:
        tags = "".join(f'<span class="tag">{html.escape(t)}</span>' for t in p.tags)
        items.append(
            f"""      <li class="post" data-node="{html.escape(p.slug)}" data-node-href="{p.url}">
        <a class="post__link" href="{p.url}">
          <h3 class="post__title">{html.escape(p.title)}</h3>
          <span class="post__date">{p.iso_date}</span>
          <p class="post__desc">{html.escape(p.description)}</p>
          <span class="post__tags">{tags}</span>
        </a>
      </li>"""
        )
    return "\n".join(items)


def splice(path: Path, replacement: str) -> bool:
    """Replace the text between the posts markers. Returns True if changed."""
    text = path.read_text(encoding="utf-8")
    if POSTS_START not in text or POSTS_END not in text:
        raise BuildError(
            f"{path}: missing {POSTS_START} / {POSTS_END} markers — "
            "build.py needs them to know what to rewrite"
        )

    head, rest = text.split(POSTS_START, 1)
    _, tail = rest.split(POSTS_END, 1)
    updated = f"{head}{POSTS_START}\n{replacement}\n      {POSTS_END}{tail}"

    if updated == text:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# Feeds
# ---------------------------------------------------------------------------


def render_feed(posts: list[Post]) -> str:
    updated = posts[0].rfc3339 if posts else f"{dt.date.today().isoformat()}T00:00:00Z"
    entries = "\n".join(
        f"""  <entry>
    <title>{sx.escape(p.title)}</title>
    <link href="{p.abs_url}"/>
    <id>{p.abs_url}</id>
    <updated>{p.rfc3339}</updated>
    <summary>{sx.escape(p.description)}</summary>
  </entry>"""
        for p in posts
    )
    return f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>{SITE_TITLE} &#8212; Writing</title>
  <subtitle>Notes on security research, Python and networking.</subtitle>
  <link href="{SITE_URL}/feed.xml" rel="self"/>
  <link href="{SITE_URL}/"/>
  <id>{SITE_URL}/</id>
  <updated>{updated}</updated>
  <author>
    <name>{AUTHOR}</name>
    <uri>{SITE_URL}</uri>
  </author>

{entries}
</feed>
"""


def render_sitemap(posts: list[Post]) -> str:
    urls = [(f"{SITE_URL}/", "1.0"), (f"{SITE_URL}/writing/", "0.8")]
    urls += [(p.abs_url, "0.7") for p in posts]
    body = "\n".join(
        f"  <url>\n    <loc>{loc}</loc>\n    <priority>{pri}</priority>\n  </url>"
        for loc, pri in urls
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{body}\n</urlset>\n"
    )


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


def load_posts(include_drafts: bool = False) -> list[Post]:
    if not SRC.is_dir():
        raise BuildError(f"no source directory: {SRC}")

    posts = [load_post(p) for p in sorted(SRC.glob("*.md"))]

    seen: dict[str, Path] = {}
    for p in posts:
        if p.slug in seen:
            raise BuildError(f"duplicate slug {p.slug!r}: {seen[p.slug]} and {p.source}")
        seen[p.slug] = p.source

    if not include_drafts:
        posts = [p for p in posts if not p.draft]

    return sorted(posts, key=lambda p: p.date, reverse=True)


def build(include_drafts: bool = False, quiet: bool = False) -> list[Post]:
    posts = load_posts(include_drafts)

    def say(msg: str) -> None:
        if not quiet:
            print(msg)

    # Drop generated post directories that no longer have a source file, so a
    # renamed or deleted post doesn't linger as a live page.
    keep = {p.slug for p in posts}
    for child in OUT.iterdir() if OUT.is_dir() else []:
        if child.is_dir() and child.name not in keep and (child / "index.html").exists():
            shutil.rmtree(child)
            say(f"  removed  writing/{child.name}/")

    for post in posts:
        target = OUT / post.slug / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render_post_page(post), encoding="utf-8")
        flag = " [draft]" if post.draft else ""
        say(f"  wrote    {target.relative_to(ROOT)}{flag}")

    if splice(OUT / "index.html", render_post_list(posts)):
        say("  updated  writing/index.html")
    if splice(ROOT / "index.html", render_post_list(posts[:HOME_POST_LIMIT])):
        say("  updated  index.html")

    (ROOT / "feed.xml").write_text(render_feed(posts), encoding="utf-8")
    (ROOT / "sitemap.xml").write_text(render_sitemap(posts), encoding="utf-8")
    say("  wrote    feed.xml, sitemap.xml")

    say(f"\n{len(posts)} post(s) built.")
    return posts


NEW_TEMPLATE = """---
title: {title}
date: {date}
description: One sentence that shows up on the index and in the feed.
tags: python, security
draft: true
---

Opening paragraph.

## A section

Body text with `inline code`, **bold**, and a [link](https://example.com).

```python
def hello() -> str:
    return "world"
```
"""


def new_post(title: str) -> Path:
    SRC.mkdir(parents=True, exist_ok=True)
    today = dt.date.today()
    path = SRC / f"{today.isoformat()}-{slugify(title)}.md"
    if path.exists():
        raise BuildError(f"{path} already exists")
    path.write_text(NEW_TEMPLATE.format(title=title, date=today.isoformat()), encoding="utf-8")
    return path


def watch() -> None:
    watched = [ROOT / "build.py", SRC]
    print("watching for changes — Ctrl-C to stop")
    last: dict[Path, float] = {}
    while True:
        stamps = {}
        for target in watched:
            files = target.rglob("*") if target.is_dir() else [target]
            for f in files:
                if f.is_file():
                    stamps[f] = f.stat().st_mtime
        if stamps != last:
            if last:
                print(f"\n[{dt.datetime.now():%H:%M:%S}] rebuilding")
            try:
                build(include_drafts=True, quiet=bool(last))
            except BuildError as exc:
                print(f"  error: {exc}", file=sys.stderr)
            last = stamps
        time.sleep(0.6)


def serve(port: int) -> None:
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(ROOT), **kw)

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def log_message(self, fmt, *args):
            pass

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", port), Handler) as httpd:
        print(f"\nserving {ROOT} at http://localhost:{port}/  (Ctrl-C to stop)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")


def main() -> int:
    ap = argparse.ArgumentParser(description="Build tylergunn.me writeups.")
    ap.add_argument("--serve", action="store_true", help="build, then serve locally")
    ap.add_argument("--watch", action="store_true", help="rebuild on file change")
    ap.add_argument("--port", type=int, default=8000, help="port for --serve")
    ap.add_argument("--drafts", action="store_true", help="include posts marked draft")
    ap.add_argument("--new", metavar="TITLE", help="scaffold a new post and exit")
    args = ap.parse_args()

    try:
        if args.new:
            path = new_post(args.new)
            print(f"created {path.relative_to(ROOT)}")
            return 0

        if args.watch:
            watch()
            return 0

        build(include_drafts=args.drafts)

        if args.serve:
            serve(args.port)
    except BuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
