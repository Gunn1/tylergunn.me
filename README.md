# tylergunn.me

Personal site. Hand-written HTML, CSS and JavaScript — **no framework, no build
step, no dependencies, no third-party requests**. Whatever is in this directory
is exactly what gets served.

## Layout

```
.
├── index.html              home — hero, work, writing, about, contact
├── 404.html                terminal-flavoured not-found page
├── writing/index.html      post index
├── assets/
│   ├── css/style.css       design tokens, layout, components
│   ├── css/terminal.css    the terminal overlay
│   ├── js/theme-init.js    applies saved theme before first paint
│   ├── js/site.js          theme toggle, scrollspy, reveals, typed roles
│   ├── js/terminal.js      the shell
│   └── img/favicon.svg
├── _headers                Cloudflare: CSP + security + cache headers
├── _redirects              Cloudflare: www→apex, /blog→/writing, short links
├── robots.txt
├── sitemap.xml
└── feed.xml
```

## Running it locally

Any static file server works. With Python:

```sh
python3 -m http.server 8000
```

Then open <http://localhost:8000>. Note that `_headers` and `_redirects` are
Cloudflare-specific and are ignored locally.

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
   - **Build command:** *(leave empty)*
   - **Build output directory:** `/`
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
- [ ] **Posts** — three entries duplicated in `index.html`, `writing/index.html`
      and `feed.xml`; the individual post pages don't exist yet
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
