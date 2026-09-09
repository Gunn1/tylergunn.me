# tylergunn.me

Personal site. Hand-written HTML, CSS and JavaScript with a **Python build
script for the writeups**. No framework, no npm, no third-party requests — the
only tooling is `build.py`, which uses nothing outside the standard library.

## Layout

```
.
├── build.py                writeup builder (stdlib only)
├── content/writeups/*.md   ← you edit these
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

## Writing a post

```sh
python3 build.py --new "Title of the post"   # scaffolds content/writeups/<date>-<slug>.md
python3 build.py --watch                     # rebuild on save, drafts included
python3 build.py --serve                     # build once, then serve on :8000
python3 build.py                             # build once, skipping drafts
```

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

It rewrites **only** what sits between the `<!-- posts:start -->` and
`<!-- posts:end -->` markers, so the rest of those two pages stays hand-editable.

The Markdown support is a deliberate subset: headings, paragraphs, fenced code,
lists, tables, blockquotes, rules, images, links, `inline code`, bold, italic and
strikethrough. It errors loudly with a file and line number rather than guessing,
and exits non-zero so a failed build is never published.

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

- [ ] **Projects** — the four cards in `index.html` (`sentinel`, `glasshouse`,
      `cutline`, `this-site`) and their GitHub URLs
- [ ] **Posts** — the three files in `content/writeups/`. These are invented;
      replace or delete them and run `python3 build.py`
- [ ] **Stats** — `data-count` values in the hero (years, projects, CTFs)
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
