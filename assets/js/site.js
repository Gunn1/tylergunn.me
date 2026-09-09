/* ==========================================================================
   site.js — progressive enhancement only.
   Everything here is optional; the page is fully readable without it.
   ========================================================================== */

(function () {
  'use strict';

  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------------------------------------------------------------- theme */

  var root = document.documentElement;
  var toggle = document.getElementById('theme-toggle');

  function setTheme(name) {
    root.dataset.theme = name;
    try {
      localStorage.setItem('theme', name);
    } catch (e) {}
    document.dispatchEvent(new CustomEvent('themechange', { detail: name }));
  }

  if (toggle) {
    toggle.addEventListener('click', function () {
      setTheme(root.dataset.theme === 'light' ? 'dark' : 'light');
    });
  }

  // The terminal's `theme` command routes through here.
  window.__setTheme = setTheme;

  /* --------------------------------------------------------- sticky header */

  var header = document.getElementById('site-header');

  if (header) {
    var onScroll = function () {
      header.dataset.stuck = window.scrollY > 8 ? 'true' : 'false';
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
  }

  /* ------------------------------------------------------------ scrollspy */

  var navLinks = Array.prototype.slice.call(document.querySelectorAll('.nav__link'));
  var sections = navLinks
    .map(function (link) {
      var id = link.getAttribute('href');
      return id && id.charAt(0) === '#' ? document.querySelector(id) : null;
    })
    .filter(Boolean);

  if (sections.length && 'IntersectionObserver' in window) {
    var spy = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          navLinks.forEach(function (link) {
            var active = link.getAttribute('href') === '#' + entry.target.id;
            if (active) {
              link.setAttribute('aria-current', 'true');
            } else {
              link.removeAttribute('aria-current');
            }
          });
        });
      },
      { rootMargin: '-45% 0px -50% 0px' }
    );
    sections.forEach(function (s) {
      spy.observe(s);
    });
  }

  /* -------------------------------------------------------- scroll reveal */

  var revealables = document.querySelectorAll('[data-reveal]');

  // Tells the failsafe in theme-init.js that the reveal is handled here.
  window.__revealReady = true;

  if (reduceMotion || !('IntersectionObserver' in window)) {
    revealables.forEach(function (el) {
      el.classList.add('is-visible');
    });
  } else {
    var revealer = new IntersectionObserver(
      function (entries, obs) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          entry.target.classList.add('is-visible');
          obs.unobserve(entry.target);
        });
      },
      // threshold 0 (not a ratio) so sections taller than the viewport still
      // trigger — the negative bottom margin already provides the delay.
      { rootMargin: '0px 0px -12% 0px', threshold: 0 }
    );
    revealables.forEach(function (el) {
      revealer.observe(el);
    });
  }

  /* ------------------------------------------------------- counting stats */

  var counters = document.querySelectorAll('[data-count]');

  if (counters.length && !reduceMotion && 'IntersectionObserver' in window) {
    var countObserver = new IntersectionObserver(
      function (entries, obs) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          obs.unobserve(entry.target);
          runCount(entry.target);
        });
      },
      { threshold: 0.5 }
    );
    counters.forEach(function (el) {
      countObserver.observe(el);
    });
  }

  function runCount(el) {
    var target = parseInt(el.dataset.count, 10);
    var suffix = el.dataset.suffix || '';
    if (isNaN(target)) return;

    var duration = 900;
    var start = null;

    function step(ts) {
      if (start === null) start = ts;
      var p = Math.min((ts - start) / duration, 1);
      // easeOutExpo — fast start, gentle settle
      var eased = p === 1 ? 1 : 1 - Math.pow(2, -10 * p);
      el.textContent = Math.round(target * eased) + suffix;
      if (p < 1) requestAnimationFrame(step);
    }

    el.textContent = '0' + suffix;
    requestAnimationFrame(step);
  }

  /* ---------------------------------------------------- typed role marquee */

  var roleEl = document.getElementById('role-text');

  var ROLES = [
    'security engineer',
    'systems programmer',
    'breaker of things',
    'writer of small sharp tools'
  ];

  if (roleEl) {
    if (reduceMotion) {
      roleEl.textContent = ROLES[0];
    } else {
      typeLoop(roleEl, ROLES);
    }
  }

  function typeLoop(el, words) {
    var i = 0;
    var chars = 0;
    var deleting = false;

    function tick() {
      var word = words[i];

      chars += deleting ? -1 : 1;
      el.textContent = word.slice(0, chars);

      var delay = deleting ? 38 : 62;

      if (!deleting && chars === word.length) {
        deleting = true;
        delay = 1900; // hold the finished word
      } else if (deleting && chars === 0) {
        deleting = false;
        i = (i + 1) % words.length;
        delay = 320;
      }

      setTimeout(tick, delay);
    }

    tick();
  }

  /* ------------------------------------------------------------- footer yr */

  var year = document.getElementById('year');
  if (year) year.textContent = String(new Date().getFullYear());
})();
