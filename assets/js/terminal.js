/* ==========================================================================
   terminal.js

   A small shell that navigates this site. The filesystem is not hardcoded —
   it is read out of the DOM at call time:

     <section data-dir="projects">        becomes  ~/projects
       <article data-node="sentinel">     becomes  ~/projects/sentinel

   So the terminal can never drift out of sync with the page content.
   ========================================================================== */

(function () {
  'use strict';

  var term = document.getElementById('term');
  if (!term) return;

  var body = document.getElementById('term-body');
  var form = document.getElementById('term-form');
  var input = document.getElementById('term-input');
  var pathEl = document.getElementById('term-path');
  var openBtn = document.getElementById('term-open');
  var closeBtn = document.getElementById('term-close');

  var cwd = '~';
  var history = [];
  var histIdx = -1;
  var draft = '';
  var lastFocus = null;
  var booted = false;

  /* ======================================================== virtual filesystem */

  // Files that live at the root alongside the section directories.
  var ROOT_FILES = {
    'README.md': {
      desc:
        'Static HTML, CSS and JavaScript with Python build scripts. No framework, ' +
        'no dependencies, no third-party requests. Written with Claude Code; ' +
        'this shell reads its filesystem directly out of the page you are looking at.'
    }
  };

  function dirElements() {
    return Array.prototype.slice
      .call(document.querySelectorAll('[data-dir]'))
      .filter(function (el) {
        return el.dataset.dir !== '~';
      });
  }

  function dirNames() {
    return dirElements().map(function (el) {
      return el.dataset.dir;
    });
  }

  function dirElement(name) {
    return document.querySelector('[data-dir="' + cssEscape(name) + '"]');
  }

  function nodesIn(dirName) {
    var el = dirElement(dirName);
    if (!el) return [];
    return Array.prototype.slice.call(el.querySelectorAll('[data-node]'));
  }

  // Entries visible in a directory: [{ name, type, el, href, desc }]
  function listing(dir) {
    if (dir === '~') {
      var entries = dirNames().map(function (name) {
        return { name: name, type: 'dir', href: '#' + (dirElement(name) || {}).id };
      });
      Object.keys(ROOT_FILES).forEach(function (name) {
        entries.push({
          name: name,
          type: 'file',
          href: ROOT_FILES[name].href,
          desc: ROOT_FILES[name].desc
        });
      });
      return entries;
    }

    return nodesIn(dir).map(function (el) {
      return {
        name: el.dataset.node,
        type: 'file',
        el: el,
        href: el.dataset.nodeHref
      };
    });
  }

  function findEntry(dir, name) {
    var hit = null;
    listing(dir).forEach(function (e) {
      if (e.name === name) hit = e;
    });
    return hit;
  }

  // Resolve a user-supplied argument to an entry, searching the cwd first and
  // then every directory — so `cat ReqFlow` works from anywhere.
  function resolve(name) {
    if (!name) return null;
    name = name.replace(/^\.\//, '').replace(/\/$/, '');

    var direct = findEntry(cwd, name);
    if (direct) return direct;

    if (cwd !== '~') {
      var atRoot = findEntry('~', name);
      if (atRoot) return atRoot;
    }

    var found = null;
    dirNames().forEach(function (d) {
      if (found) return;
      var e = findEntry(d, name);
      if (e) found = e;
    });
    return found;
  }

  /* ================================================================= output */

  function esc(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function cssEscape(s) {
    return String(s).replace(/["\\]/g, '\\$&');
  }

  function line(html, cls) {
    var el = document.createElement('div');
    el.className = 'term__line' + (cls ? ' term__line--' + cls : '');
    el.innerHTML = html;
    body.appendChild(el);
    return el;
  }

  function out(text, cls) {
    line(esc(text), cls);
  }

  function blank() {
    line('&nbsp;');
  }

  function err(text) {
    out(text, 'err');
  }

  function scrollDown() {
    body.scrollTop = body.scrollHeight;
  }

  // Soft-wrap prose at a comfortable measure so long paragraphs stay readable.
  function wrap(text, width) {
    width = width || 74;
    var words = String(text).replace(/\s+/g, ' ').trim().split(' ');
    var lines = [];
    var cur = '';

    words.forEach(function (w) {
      if (!cur.length) {
        cur = w;
      } else if ((cur + ' ' + w).length <= width) {
        cur += ' ' + w;
      } else {
        lines.push(cur);
        cur = w;
      }
    });
    if (cur.length) lines.push(cur);
    return lines;
  }

  function paragraph(text, cls) {
    wrap(text).forEach(function (l) {
      out(l, cls);
    });
  }

  function textOf(el, sel) {
    var node = el.querySelector(sel);
    return node ? node.textContent.replace(/\s+/g, ' ').trim() : '';
  }

  /* =============================================================== commands */

  var COMMANDS = {};

  function define(name, meta) {
    COMMANDS[name] = meta;
  }

  define('help', {
    usage: 'help',
    about: 'list available commands',
    run: function () {
      blank();
      out('Available commands', 'ok');
      blank();

      var names = Object.keys(COMMANDS).filter(function (n) {
        return !COMMANDS[n].hidden;
      });

      var pad = names.reduce(function (m, n) {
        return Math.max(m, COMMANDS[n].usage.length);
      }, 0);

      names.forEach(function (n) {
        var c = COMMANDS[n];
        var padded = c.usage + Array(pad - c.usage.length + 3).join(' ');
        line('  <span class="k">' + esc(padded) + '</span><span class="d">' + esc(c.about) + '</span>');
      });

      blank();
      line('<span class="d">Tab completes · ↑/↓ walks history · Esc closes · there are a few things in here that are not on this list</span>');
      blank();
    }
  });

  define('ls', {
    usage: 'ls [-l] [dir]',
    about: 'list directory contents',
    run: function (args) {
      var long = args.indexOf('-l') !== -1;
      var rest = args.filter(function (a) {
        return a.charAt(0) !== '-';
      });
      var target = rest[0] ? rest[0].replace(/\/$/, '') : cwd;

      if (target !== '~' && target !== cwd && dirNames().indexOf(target) === -1) {
        var entry = resolve(target);
        if (entry && entry.type === 'file') {
          out(entry.name);
          return;
        }
        err('ls: ' + target + ': No such file or directory');
        return;
      }

      var entries = listing(target === '~' ? '~' : target);
      if (!entries.length) {
        out('(empty)', 'dim');
        return;
      }

      if (long) {
        entries.forEach(function (e) {
          var perm = e.type === 'dir' ? 'drwxr-xr-x' : '-rw-r--r--';
          var size = String(120 + e.name.length * 37).padStart(6, ' ');
          line(
            '<span class="d">' + perm + '  tyler  ' + size + '  </span>' +
              '<span class="' + e.type + '">' + esc(e.name) + (e.type === 'dir' ? '/' : '') + '</span>'
          );
        });
        return;
      }

      var html = entries
        .map(function (e) {
          return (
            '<span class="' + e.type + '">' + esc(e.name) + (e.type === 'dir' ? '/' : '') + '</span>'
          );
        })
        .join('');
      line('<div class="term__grid">' + html + '</div>');
    }
  });

  define('cd', {
    usage: 'cd <dir>',
    about: 'change directory — also scrolls the page there',
    run: function (args) {
      var target = (args[0] || '~').replace(/\/$/, '');

      if (target === '~' || target === '/' || target === '..') {
        cwd = '~';
        setPath();
        window.scrollTo({ top: 0, behavior: 'smooth' });
        return;
      }

      if (dirNames().indexOf(target) === -1) {
        err('cd: ' + target + ': No such file or directory');
        return;
      }

      cwd = target;
      setPath();

      var el = dirElement(target);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        line('<span class="d">→ scrolled to </span><span class="k">#' + esc(el.id) + '</span>');
      }
    }
  });

  define('pwd', {
    usage: 'pwd',
    about: 'print working directory',
    run: function () {
      out(cwd === '~' ? '/home/tyler' : '/home/tyler/' + cwd);
    }
  });

  define('cat', {
    usage: 'cat <file>',
    about: 'read a project, post or file',
    run: function (args) {
      if (!args[0]) {
        err('cat: missing operand');
        return;
      }

      var name = args[0].replace(/\/$/, '');

      if (dirNames().indexOf(name) !== -1) {
        err('cat: ' + name + ': Is a directory');
        return;
      }

      var entry = resolve(name);
      if (!entry) {
        err('cat: ' + name + ': No such file or directory');
        return;
      }

      blank();

      // Root-level pseudo-files carry their own copy.
      if (!entry.el) {
        line('<b>' + esc(entry.name) + '</b>');
        blank();
        paragraph(entry.desc || '(empty)');
        if (entry.href) {
          blank();
          line('<span class="d">open: </span><a href="' + esc(entry.href) + '">' + esc(entry.href) + '</a>');
        }
        blank();
        return;
      }

      var el = entry.el;
      var title = textOf(el, '.card__title') || textOf(el, '.post__title') || entry.name;
      var kind = textOf(el, '.card__kind');
      var date = textOf(el, '.post__date');
      var desc = textOf(el, '.card__desc') || textOf(el, '.post__desc');

      line('<b>' + esc(title) + '</b>' + (kind ? ' <span class="w">[' + esc(kind) + ']</span>' : ''));
      if (date) line('<span class="d">' + esc(date) + '</span>');
      blank();

      if (desc) {
        paragraph(desc);
      } else {
        // Fall back to the element's own prose (bio.txt, skills.txt).
        var paras = el.querySelectorAll('p, li');
        if (paras.length) {
          Array.prototype.forEach.call(paras, function (p, i) {
            var t = p.textContent.replace(/\s+/g, ' ').trim();
            if (!t) return;
            if (p.tagName === 'LI') {
              out('  · ' + t);
            } else {
              if (i) blank();
              paragraph(t);
            }
          });
        } else {
          paragraph(el.textContent);
        }
      }

      var tags = el.querySelectorAll('.tag');
      if (tags.length) {
        blank();
        line(
          '<span class="d">tags: </span>' +
            Array.prototype.map
              .call(tags, function (t) {
                return '<span class="w">' + esc(t.textContent.trim()) + '</span>';
              })
              .join('<span class="d">, </span>')
        );
      }

      if (entry.href) {
        blank();
        line('<span class="d">$ open ' + esc(entry.name) + '</span>  <a href="' + esc(entry.href) + '">' + esc(entry.href) + '</a>');
      }

      blank();
    }
  });

  define('open', {
    usage: 'open <file>',
    about: 'open a project, post or link',
    run: function (args) {
      if (!args[0]) {
        err('open: missing operand');
        return;
      }

      var name = args[0].replace(/\/$/, '');

      if (dirNames().indexOf(name) !== -1) {
        return COMMANDS.cd.run([name]);
      }

      var entry = resolve(name);
      if (!entry) {
        err('open: ' + name + ': No such file or directory');
        return;
      }
      if (!entry.href) {
        err('open: ' + name + ': nothing to open — try `cat ' + name + '`');
        return;
      }

      var href = entry.href;
      out('Opening ' + href + ' …', 'ok');

      if (/^https?:/i.test(href)) {
        window.open(href, '_blank', 'noopener');
      } else if (href.charAt(0) === '#') {
        close();
        var el = document.querySelector(href);
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      } else {
        window.location.href = href;
      }
    }
  });

  define('whoami', {
    usage: 'whoami',
    about: 'who is this guy',
    run: function () {
      blank();
      line('<b>Tyler Gunn</b> <span class="d">— IT project manager · automation · security research</span>');
      blank();
      paragraph(
        'I manage IT projects at an MSP and build the automation around them — ' +
          'mostly asset-management integrations in Python. On the side I do ' +
          'security research: understanding how something is built is the fastest ' +
          'route to understanding how it breaks.'
      );
      blank();
      line('<span class="d">Try </span><span class="k">ls</span><span class="d">, </span><span class="k">cat ReqFlow</span><span class="d">, or </span><span class="k">contact</span><span class="d">.</span>');
      blank();
    }
  });

  define('contact', {
    usage: 'contact',
    about: 'ways to reach me',
    run: function () {
      blank();
      var rows = [
        ['email', 'tylerjgunn@gmail.com', 'mailto:tylerjgunn@gmail.com'],
        ['github', 'github.com/Gunn1', 'https://github.com/Gunn1'],
        ['linkedin', 'in/tyler-gunn', 'https://www.linkedin.com/in/tyler-gunn-5ab508242/'],
        ['site', 'tylergunn.me', 'https://tylergunn.me']
      ];
      var html = rows
        .map(function (r) {
          return '<dt>' + esc(r[0]) + '</dt><dd><a href="' + esc(r[2]) + '">' + esc(r[1]) + '</a></dd>';
        })
        .join('');
      line('<dl class="term__kv">' + html + '</dl>');
      blank();
    }
  });

  define('theme', {
    usage: 'theme [dark|light]',
    about: 'switch colour scheme',
    run: function (args) {
      var want = (args[0] || '').toLowerCase();
      var current = document.documentElement.dataset.theme;

      if (!want) {
        out('theme is ' + current + ' — usage: theme [dark|light]', 'dim');
        return;
      }
      if (want !== 'dark' && want !== 'light') {
        err('theme: unknown theme "' + want + '" (expected dark or light)');
        return;
      }
      if (window.__setTheme) window.__setTheme(want);
      out('theme → ' + want, 'ok');
    }
  });

  define('neofetch', {
    usage: 'neofetch',
    about: 'system information, obviously',
    run: function () {
      var art = [
        ' ████████  ██████ ',
        '    ██    ██      ',
        '    ██    ██  ███ ',
        '    ██    ██   ██ ',
        '    ██     █████  '
      ];

      var info = [
        ['user', 'tyler@gunn'],
        ['os', 'the web, unfortunately'],
        ['shell', 'tgsh 1.0'],
        ['host', 'tylergunn.me'],
        ['uptime', uptime()],
        ['langs', 'Python, Bash, C'],
        ['deps', '0'],
        ['theme', document.documentElement.dataset.theme]
      ];

      blank();
      art.forEach(function (l) {
        out(l, 'art');
      });
      blank();
      line(
        '<dl class="term__kv">' +
          info
            .map(function (r) {
              return '<dt>' + esc(r[0]) + '</dt><dd>' + esc(r[1]) + '</dd>';
            })
            .join('') +
          '</dl>'
      );
      blank();
    }
  });

  define('history', {
    usage: 'history',
    about: 'show command history',
    run: function () {
      if (!history.length) {
        out('(no history)', 'dim');
        return;
      }
      history.forEach(function (h, i) {
        line('<span class="d">' + String(i + 1).padStart(4, ' ') + '  </span>' + esc(h));
      });
    }
  });

  define('clear', {
    usage: 'clear',
    about: 'clear the screen',
    run: function () {
      body.innerHTML = '';
    }
  });

  define('exit', {
    usage: 'exit',
    about: 'close the terminal',
    run: function () {
      out('logout');
      setTimeout(close, 160);
    }
  });

  /* --- undocumented --- */

  define('sudo', {
    usage: 'sudo',
    about: '',
    hidden: true,
    run: function (args) {
      if (!args.length) {
        err('usage: sudo <command>');
        return;
      }
      out('[sudo] password for guest: ', 'dim');
      err('guest is not in the sudoers file. This incident has been reported.');
      out('…to nobody. It is a static site.', 'dim');
    }
  });

  define('echo', {
    usage: 'echo <text>',
    about: '',
    hidden: true,
    run: function (args) {
      out(args.join(' '));
    }
  });

  define('uname', {
    usage: 'uname',
    about: '',
    hidden: true,
    run: function () {
      out('tgsh 1.0 (' + navigator.platform + ') — static, stateless, suspiciously fast');
    }
  });

  define('date', {
    usage: 'date',
    about: '',
    hidden: true,
    run: function () {
      out(new Date().toString());
    }
  });

  define('rm', {
    usage: 'rm',
    about: '',
    hidden: true,
    run: function (args) {
      if (args.indexOf('-rf') !== -1 || args.indexOf('-fr') !== -1) {
        out('Nice try.', 'w');
        out('This whole filesystem is regenerated from the DOM on every command.', 'dim');
        return;
      }
      err('rm: read-only filesystem');
    }
  });

  define('nmap', {
    usage: 'nmap',
    about: '',
    hidden: true,
    run: function () {
      blank();
      out('Starting Nmap 7.99 ( https://nmap.org )');
      out('Nmap scan report for tylergunn.me');
      blank();
      line('<span class="d">PORT    STATE  SERVICE</span>');
      line('443/tcp <span class="k">open</span>   https  <span class="d">(Cloudflare)</span>');
      line('80/tcp  <span class="k">open</span>   http   <span class="d">(→ 301 https)</span>');
      line('22/tcp  <span class="d">filtered</span> ssh');
      blank();
      out('Nothing else. It is a static site — there is no backend to find.', 'dim');
      blank();
    }
  });

  define('man', {
    usage: 'man',
    about: '',
    hidden: true,
    run: function (args) {
      if (!args[0]) {
        err('What manual page do you want?');
        return;
      }
      var c = COMMANDS[args[0]];
      if (!c) {
        err('No manual entry for ' + args[0]);
        return;
      }
      blank();
      out(args[0].toUpperCase() + '(1)');
      blank();
      out('  ' + c.usage);
      if (c.about) out('  ' + c.about, 'dim');
      blank();
    }
  });

  /* ================================================================== shell */

  function setPath() {
    pathEl.textContent = cwd;
  }

  function prompt(cmd) {
    line(
      '<span class="k">tyler@gunn</span><span class="d">:</span>' +
        '<span class="d">' + esc(cwd) + '</span><span class="d">$</span> ' +
        esc(cmd),
      'cmd'
    );
  }

  function exec(raw) {
    var trimmed = raw.trim();
    prompt(trimmed);

    if (!trimmed) return;

    history.push(trimmed);
    histIdx = history.length;

    var parts = trimmed.split(/\s+/);
    var name = parts[0];
    var args = parts.slice(1);

    var cmd = COMMANDS[name];
    if (!cmd) {
      err(name + ': command not found');
      out("Type 'help' for a list of commands.", 'dim');
      return;
    }

    try {
      cmd.run(args);
    } catch (e) {
      err(name + ': ' + e.message);
    }
  }

  /* --------------------------------------------------------- tab completion */

  function complete() {
    var value = input.value;
    var parts = value.split(/\s+/);
    var isFirst = parts.length === 1;
    var frag = parts[parts.length - 1];

    var pool = isFirst
      ? Object.keys(COMMANDS).filter(function (n) {
          return !COMMANDS[n].hidden;
        })
      : listing(cwd)
          .map(function (e) {
            return e.name;
          })
          .concat(cwd === '~' ? [] : dirNames());

    var matches = pool.filter(function (n) {
      return n.indexOf(frag) === 0;
    });

    if (!matches.length) return;

    if (matches.length === 1) {
      parts[parts.length - 1] = matches[0];
      input.value = parts.join(' ') + ' ';
      return;
    }

    // Extend to the longest common prefix, then show the options.
    var prefix = matches.reduce(function (acc, m) {
      var i = 0;
      while (i < acc.length && i < m.length && acc[i] === m[i]) i++;
      return acc.slice(0, i);
    });

    if (prefix.length > frag.length) {
      parts[parts.length - 1] = prefix;
      input.value = parts.join(' ');
    }

    prompt(value);
    line(
      '<div class="term__grid">' +
        matches
          .map(function (m) {
            return '<span class="file">' + esc(m) + '</span>';
          })
          .join('') +
        '</div>'
    );
    scrollDown();
  }

  /* ------------------------------------------------------------ open / close */

  function uptime() {
    var s = Math.floor(performance.now() / 1000);
    if (s < 60) return s + 's';
    var m = Math.floor(s / 60);
    return m + 'm ' + (s % 60) + 's';
  }

  function boot() {
    if (booted) return;
    booted = true;

    line('<b>tgsh 1.0</b> <span class="d">— tylergunn.me interactive shell</span>');
    line('<span class="d">This shell reads its filesystem out of the page itself.</span>');
    blank();
    line(
      '<span class="d">Type </span><span class="k">help</span><span class="d"> for commands, or try </span>' +
        '<span class="k">whoami</span><span class="d"> · </span>' +
        '<span class="k">ls</span><span class="d"> · </span>' +
        '<span class="k">cat ReqFlow</span><span class="d"> · </span>' +
        '<span class="k">neofetch</span>'
    );
    blank();
  }

  function open() {
    if (term.dataset.open === 'true') return;
    lastFocus = document.activeElement;
    term.dataset.open = 'true';
    term.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
    boot();
    setPath();
    setTimeout(function () {
      input.focus();
      scrollDown();
    }, 60);
  }

  function close() {
    if (term.dataset.open !== 'true') return;
    term.dataset.open = 'false';
    term.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  window.__openTerminal = open;

  /* ================================================================ wiring */

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var value = input.value;
    input.value = '';
    draft = '';
    exec(value);
    scrollDown();
  });

  input.addEventListener('keydown', function (e) {
    if (e.key === 'Tab') {
      e.preventDefault();
      complete();
      return;
    }

    if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (!history.length) return;
      if (histIdx === history.length) draft = input.value;
      histIdx = Math.max(0, histIdx - 1);
      input.value = history[histIdx];
      moveCaretToEnd();
      return;
    }

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (histIdx >= history.length) return;
      histIdx++;
      input.value = histIdx === history.length ? draft : history[histIdx];
      moveCaretToEnd();
      return;
    }

    if (e.key === 'l' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      body.innerHTML = '';
      return;
    }

    if (e.key === 'c' && e.ctrlKey && !window.getSelection().toString()) {
      e.preventDefault();
      prompt(input.value + '^C');
      input.value = '';
      scrollDown();
    }
  });

  function moveCaretToEnd() {
    requestAnimationFrame(function () {
      input.setSelectionRange(input.value.length, input.value.length);
    });
  }

  // Clicking anywhere in the scrollback refocuses the input, unless the user
  // is selecting text or following a link.
  body.addEventListener('mouseup', function (e) {
    if (e.target.closest('a')) return;
    if (window.getSelection().toString()) return;
    input.focus();
  });

  if (openBtn) openBtn.addEventListener('click', open);
  if (closeBtn) closeBtn.addEventListener('click', close);

  term.addEventListener('mousedown', function (e) {
    if (e.target === term) close();
  });

  document.addEventListener('keydown', function (e) {
    var isOpen = term.dataset.open === 'true';

    if (e.key === 'Escape' && isOpen) {
      e.preventDefault();
      close();
      return;
    }

    if (isOpen) return;

    // Ctrl/Cmd+K from anywhere.
    if (e.key === 'k' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      open();
      return;
    }

    // Backtick, but not while the user is typing somewhere else.
    if (e.key === '`' && !e.ctrlKey && !e.metaKey && !e.altKey) {
      var t = e.target;
      var typing =
        t &&
        (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable);
      if (typing) return;
      e.preventDefault();
      open();
    }
  });

  // Deep link: /#terminal opens the shell straight away, so the link is
  // shareable. Optional ?cmd= runs something on boot, e.g. /#terminal?cmd=whoami
  (function deepLink() {
    var hash = window.location.hash;
    if (hash.indexOf('#terminal') !== 0) return;

    open();

    var m = /[?&]cmd=([^&]+)/.exec(hash);
    if (!m) return;

    exec(decodeURIComponent(m[1].replace(/\+/g, ' ')));
    scrollDown();
  })();

  setPath();
})();
