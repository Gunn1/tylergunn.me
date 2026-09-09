/* Applies the saved theme before first paint so there is no flash of the wrong
   colour scheme. Must be loaded synchronously in <head>, before the stylesheet
   has a chance to render. Kept in its own file (rather than inline) so the site
   can ship a CSP with no 'unsafe-inline' in script-src. */
(function () {
  // Marks that scripting is alive. The scroll-reveal styles are scoped to .js,
  // so without this the content stays plainly visible instead of stuck at
  // opacity 0.
  document.documentElement.classList.add('js');

  // Failsafe: content must never be permanently invisible. If site.js hasn't
  // taken ownership of the reveal animation shortly after load — it failed to
  // parse, was blocked, arrived too late — drop the class so everything is
  // simply shown.
  window.setTimeout(function () {
    if (!window.__revealReady) {
      document.documentElement.classList.remove('js');
    }
  }, 1500);

  try {
    var saved = localStorage.getItem('theme');
    var prefersLight = window.matchMedia('(prefers-color-scheme: light)').matches;
    document.documentElement.dataset.theme = saved || (prefersLight ? 'light' : 'dark');
  } catch (e) {
    document.documentElement.dataset.theme = 'dark';
  }
})();
