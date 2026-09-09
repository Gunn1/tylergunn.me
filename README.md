# tylergunn.me

Personal site. Static HTML, CSS and JavaScript with **Python build scripts**.
Written with [Claude Code](https://claude.com/claude-code). No framework, no npm, no third-party requests — the
only tooling is `build.py`, which uses nothing outside the standard library.

## Layout

```
.
├── build.py                projects + writeups builder (stdlib only)
├── writeup.py              record notes while you work → a draft
├── ctftime.py              pulls CTF results from the CTFtime API
├── content/
│   ├── projects.toml       ← "Selected work" cards
│   ├── writeups/*.md       ← blog posts
│   └── ctf.json            cached CTF results (generated)
├── index.html              home — hero, work, writing, about, contact
├── 404.html                terminal-flavoured not-found page
├── writing/
│   ├── index.html          post index          (generated section)
│   └── <slug>/index.html   one page per post   (generated)
├── assets/
│   ├── css/style.css       design tokens, layout, components, article prose
│   ├── css/terminal.css    the terminal overlay
│   ├── js/theme-init.js    applies saved theme before first paint
│   ├── js/site.js          theme toggle, scrollspy, reveals, typed roles
│   ├── js/terminal.js      the shell
│   └── img/favicon.svg
├── _headers                Cloudflare: CSP + security + cache headers
├── _redirects              Cloudflare: www→apex, /blog→/writing, short links
├── robots.txt
├── sitemap.xml             (generated)
└── feed.xml                (generated)
```

## Editing "Selected work"

Projects live in `content/projects.toml`. Edit that file, then run
`python3 build.py`. Order in the file is order on the page.

```toml
[[project]]
name = "Google2Snipe-IT"
kind = "tool"          # tool (green) | research (amber) | anything else (grey)
featured = true        # at most one — gets the wide card with the code pane
description = """
Prose. Wraps however you like; whitespace is collapsed.
"""
tags = ["Python", "Google Admin SDK", "Snipe-IT"]
source = "https://github.com/Gunn1/Google2Snipe-IT"          # optional
writeup = "/writing/isp-monitoring-disclosure/"              # optional
demo = "https://example.com"                                 # optional

code_filename = "Google2Snipe-IT — sync.py"                  # featured card only
code = '''
# keep lines to ~44 chars or the pane scrolls
for device in paginate(admin.chromeosdevices()):
    upsert(snipe, device)
'''
```

Only `name` and `description` are required. The `code` block is syntax
highlighted automatically — a small Python highlighter in `build.py`, no
dependency.

To add a project, append a `[[project]]` block. To remove one, delete its block.
To reorder, move the blocks.

The build refuses to write anything if the file is malformed: invalid TOML, a
missing `name`/`description`, more than one `featured`, or no projects at all.
Sources are parsed and validated before any file is written, so a typo can't
leave the site half-rebuilt.

## Security section

`content/security.toml` drives the `#security` block: disclosures and platform
profiles. Either list can be empty; if both are, the section and its nav link
disappear the same way the writing section does.

```toml
[[disclosure]]
title = "Multi-stage attack chain in an ISP's LibreNMS monitoring platform"
target = "Regional ISP"
date = "2026-03"
severity = "critical"          # critical | high | medium | low
status = "remediated in one week"
summary = """Prose. Optional."""
writeup = "/writing/isp-monitoring-disclosure/"   # optional, a post on this site
ref = "https://..."                               # optional, CVE or advisory

[[profile]]
name = "TryHackMe"
handle = "yourhandle"          # optional
url = "https://tryhackme.com/p/yourhandle"
note = "Top 5%"                # optional
```

Only critical and high get a coloured badge — if everything is highlighted,
nothing is.

## Writing a post

```sh
python3 build.py --new "Title of the post"   # scaffolds content/writeups/<date>-<slug>.md
python3 build.py --dev                       # live preview — see below
python3 build.py --watch                     # rebuild on save, no server
python3 build.py --serve                     # build once, then serve on :8000
python3 build.py                             # build once, skipping drafts
```

### Recording a writeup while you work

The interesting part of a writeup is the dead ends, and those are exactly what
you've forgotten by the time you sit down to write. `writeup.py` records them as
they happen.

```sh
./writeup.py start heap-overflow "Plaid pwn 300" --tags "pwn, glibc, ctf"

./writeup.py note "length is int32, validated on the upper bound only"
./writeup.py note --fail "chased the NULL deref — mmap_min_addr is 65536"
./writeup.py note --win  "fake vtable on _IO_2_1_stdout_"
./writeup.py note --takeaway "check the environment before writing the exploit"

./writeup.py code exploit.py:40-58     # capture a file or line range
./writeup.py run checksec ./chal       # run it, capture command + output

./writeup.py status                    # what's recorded so far
./writeup.py build                     # → content/writeups/<date>-<slug>.md
```

Notes file into fixed sections — **What I tried**, **Dead ends**, **What
worked**, **Takeaways** — matching the shape of the existing posts. A code block
lands in whichever section the note before it opened, so a snippet captured
right after a `--fail` appears under Dead ends.

`build` writes the draft with `draft: true`, so it can't publish by accident.
It's visible under `--dev` while you rewrite the raw notes into prose; remove the
flag when it's ready.

Other commands: `list` (all sessions), `drop --yes` (delete one), and `-s <slug>`
to act on a session other than the active one.

Sessions live in `.writeup/` and are gitignored — they're working notes, not
output. The Markdown draft is the artifact.

### Live preview

```sh
python3 build.py --dev
```

Serves on <http://localhost:8000>, watches `content/`, rebuilds on save, and
**reloads the browser by itself**. Drafts are included. Write Markdown in one
window, watch it render in the other.

How it works: the dev server holds a Server-Sent Events connection at
`/__reload` and injects a four-line listener into HTML *as it is served*. The
files on disk never contain it, so nothing dev-only can reach production.

If a build fails, the browser is deliberately **not** reloaded — the last good
page stays on screen and the error is printed to the terminal, so you don't lose
your place to a half-rendered page.

Each Markdown file starts with a front matter block:

```
---
title: Scanning 65k ports without melting your NIC
slug: asyncio-recon          # optional, defaults to a slug of the title
date: 2026-05-02
description: One sentence for the index and the feed.
tags: python, asyncio, networking
draft: true                  # omit or set false to publish
---
```

`build.py` writes `writing/<slug>/index.html`, refreshes the post lists on the
home page and `/writing/`, and regenerates `feed.xml` and `sitemap.xml`. Deleting
a Markdown file removes its generated page on the next build.

The home page's writing block only appears once there are `HOME_WRITING_MIN`
posts (default 2). With a single post it would show the same item twice — once
in the security section, once under writing — so below the threshold the block
is omitted and the nav link points straight at `/writing/` instead. Set the
constant to 1 in `build.py` if you'd rather always show it.

It rewrites **only** what sits between the `<!-- posts:start -->` and
`<!-- posts:end -->` markers, so the rest of those two pages stays hand-editable.

The Markdown support is a deliberate subset: headings, paragraphs, fenced code,
lists, tables, blockquotes, rules, images, links, `inline code`, bold, italic and
strikethrough. It errors loudly with a file and line number rather than guessing,
and exits non-zero so a failed build is never published.

## CTF results

`ctftime.py` pulls real results from the CTFtime API into the `#ctf` section and
the hero stat. Standard library only, same marker-splice approach as `build.py`.

```sh
python3 ctftime.py              # fetch, cache to content/ctf.json, update index.html
python3 ctftime.py --offline    # rebuild the HTML from the cache, no network
python3 ctftime.py --dry-run    # print the table, write nothing
python3 ctftime.py --since 2020 # widen the scan window (default 2022)
```

Teams are configured in the `TEAMS` dict at the top of the script.

Some things about the CTFtime API that are not obvious and cost time to work out:

- **There is no endpoint that lists a team's events.** `/api/v1/teams/{id}/`
  returns aggregate rating per year and nothing else. The event list has to be
  recovered by scanning `/api/v1/results/{year}/` — every event's full
  scoreboard — for rows matching your `team_id`. That is what this script does.
- **The API returns 403 without a browser User-Agent.**
- **There is no search.** `/search/` 404s, and `/api/v1/teams/` ignores a
  `search` param, so you need the numeric team ID from the team page URL.
- **`participants` on an event is CTFtime registrations, not scoreboard size.**
  Using it for percentiles produces nonsense like "top 733%". The correct
  denominator is `len(scores)` from the results endpoint.
- **CTFtime tracks teams, not people.** These are events the *team* scored in.

## Running it locally

`python3 build.py --serve`, or any static file server:

```sh
python3 -m http.server 8000
```

Note that `_headers` and `_redirects` are Cloudflare-specific and are ignored
locally.

## The terminal

Press <kbd>`</kbd> or <kbd>Ctrl</kbd>+<kbd>K</kbd> anywhere on the site.

The interesting part: **the filesystem is not hardcoded.** `terminal.js` reads
it out of the live DOM every time a command runs:

| Markup                              | Becomes                |
| ----------------------------------- | ---------------------- |
| `<section data-dir="projects">`     | `~/projects`           |
| `<article data-node="sentinel">`    | `~/projects/sentinel`  |
| `data-node-href="..."`              | what `open` navigates to |

So adding a project card to the page automatically adds it to the shell — the
two can never drift out of sync. `cat` pulls its text from `.card__desc` /
`.post__desc` on the element itself.

Commands: `help` `ls` `cd` `pwd` `cat` `open` `whoami` `contact` `theme`
`neofetch` `history` `clear` `exit` — plus a handful that aren't in `help`.

## Deploying to Cloudflare Pages

1. Push this directory to a GitHub repo.
2. Cloudflare dashboard → **Workers & Pages** → **Create** → **Pages** →
   **Connect to Git**, and pick the repo.
3. Build settings:
   - **Framework preset:** `None`
   - **Build command:** `python3 build.py`
   - **Build output directory:** `/`

   Cloudflare Pages has Python available, so it can run the build itself. If you
   would rather not depend on that, run `python3 build.py` locally, commit the
   generated HTML, and leave the build command empty — the output is committed
   either way.
4. Deploy. You'll get a `*.pages.dev` URL immediately.
5. **Custom domains** → add `tylergunn.me` and `www.tylergunn.me`. If the domain
   is already on Cloudflare DNS the records are created for you.

Every push to `main` redeploys; pull requests get preview URLs.

### Or deploy straight from this machine

```sh
npx wrangler pages deploy . --project-name=tylergunn-me
```

(Requires Node, which isn't installed here — the Git integration above avoids
needing it at all.)

## Things to replace before going live

Everything below is placeholder content written to make the layout real. Search
for these and swap in your own:

- [ ] **Projects** — the four entries in `content/projects.toml` (`sentinel`,
      `glasshouse`, `cutline`, `tylergunn.me`) and their GitHub URLs
- [ ] **Posts** — the three files in `content/writeups/`. These are invented;
      replace or delete them and run `python3 build.py`
- [ ] **Stats** — "Years building" (6) and "Projects shipped" (24) in the hero
      are still invented. The CTF count is real and maintained by `ctftime.py`
- [ ] **Bio** — the three paragraphs in `#bio`
- [ ] **Skills** — the three groups in `.skills`
- [ ] **Social links** — `github.com/tylergunn`, `linkedin.com/in/tylergunn`
      appear in `index.html`, `_redirects`, `terminal.js` (the `contact` command)
      and the JSON-LD block
- [ ] **`whoami` / `contact`** blurbs in `assets/js/terminal.js`
- [ ] **`cv.pdf`** — drop one at the repo root
- [ ] **`assets/img/og.png`** — 1200×630 social preview image

## Notes

- Ships a strict CSP (`script-src 'self'`, no `unsafe-inline`). That's why the
  theme bootstrap lives in `theme-init.js` rather than an inline `<script>`.
- Fully functional without JavaScript: all content is real HTML. JS only adds
  the terminal, the theme toggle, and motion.
- Honours `prefers-reduced-motion` and `prefers-color-scheme`.
- Fonts are system stacks, so there are zero external requests and no CLS.
