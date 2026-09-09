/* Shows the path the visitor actually asked for in the fake `stat` output. */
(function () {
  'use strict';

  var slot = document.getElementById('badpath');
  if (slot) {
    var path = window.location.pathname.replace(/^\/+/, '') || 'the-page-you-wanted';
    // textContent, never innerHTML — the path is attacker-controlled.
    slot.textContent = path.length > 48 ? path.slice(0, 48) + '…' : path;
  }

  var year = document.getElementById('year');
  if (year) year.textContent = String(new Date().getFullYear());
})();
