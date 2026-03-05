/* ── Wezea — Footer partagé pour les pages statiques ────────────────────── */
(function () {
  var css =
    '.wz-footer{' +
    'border-top:1px solid rgba(30,41,59,.6);' +
    'background:rgba(2,6,23,.8);' +
    'padding:1rem 1.5rem;}' +

    '.wz-footer-inner{' +
    'max-width:1152px;margin:0 auto;' +
    'display:flex;flex-wrap:wrap;align-items:center;justify-content:center;' +
    'gap:.375rem 1.25rem;}' +

    '.wz-footer-inner a,.wz-footer-inner span{' +
    'font-size:12px;color:#475569;text-decoration:none;' +
    'transition:color .15s;white-space:nowrap;}' +

    '.wz-footer-inner a:hover{color:#94a3b8;text-decoration:none;}' +

    '.wz-footer-sep{color:#1e293b !important;}' +

    '@media(max-width:600px){' +
    '.wz-footer-sep{display:none;}' +
    '}';

  var styleEl = document.createElement('style');
  styleEl.textContent = css;
  document.head.appendChild(styleEl);

  var year = new Date().getFullYear();

  var footer = document.createElement('footer');
  footer.className = 'wz-footer';
  footer.innerHTML =
    '<div class="wz-footer-inner">' +
      '<span>© ' + year + ' WEZEA · BCE 0811.380.056</span>' +
      '<span class="wz-footer-sep">|</span>' +
      '<a href="/agences/">Agences</a>' +
      '<a href="/blog/">Blog</a>' +
      '<a href="https://wezea.net?legal=mentions">Mentions légales</a>' +
      '<a href="https://wezea.net?legal=confidentialite">Confidentialité & RGPD</a>' +
      '<a href="https://wezea.net?legal=cgv">CGV</a>' +
      '<a href="https://wezea.net?legal=cgu">CGU</a>' +
      '<a href="https://wezea.net?legal=cookies">Cookies</a>' +
      '<span class="wz-footer-sep">|</span>' +
      '<a href="mailto:contact@wezea.net">contact@wezea.net</a>' +
    '</div>';

  var s = document.currentScript;
  if (s && s.parentNode) {
    s.parentNode.insertBefore(footer, s);
  } else {
    document.body.appendChild(footer);
  }
})();
