/* ── Wezea — Navbar + Footer partagés pour les pages statiques ──────────── */
(function () {
  /* ── Icônes SVG ─────────────────────────────────────────────────────────── */
  var ICON_BOOK =
    '<svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">' +
    '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>' +
    '<path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>' +
    '</svg>';

  var ICON_BUILDING =
    '<svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">' +
    '<path d="M6 22V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v18Z"/>' +
    '<path d="M6 12H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2"/>' +
    '<path d="M18 9h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-2"/>' +
    '<path d="M10 6h4"/><path d="M10 10h4"/><path d="M10 14h4"/><path d="M10 18h4"/>' +
    '</svg>';

  /* ── CSS navbar + footer ────────────────────────────────────────────────── */
  var css =
    /* — Navbar — */
    '.wz-nav{position:sticky;top:0;z-index:50;' +
    'backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);' +
    'background:linear-gradient(180deg,rgba(22,28,36,.97) 0%,rgba(13,17,23,.97) 100%);' +
    'border-bottom:1px solid rgba(255,255,255,.07);' +
    'box-shadow:0 4px 24px rgba(0,0,0,.6),0 1px 0 rgba(255,255,255,.03) inset;}' +

    '.wz-nav-inner{max-width:1152px;margin:0 auto;padding:0 1.25rem;height:52px;' +
    'display:flex;align-items:center;gap:1rem;}' +

    '.wz-nav-logo{font-size:20px;font-weight:900;color:#fff;letter-spacing:-.03em;' +
    'font-family:-apple-system,"SF Pro Display","Inter",system-ui,sans-serif;' +
    'text-decoration:none;flex-shrink:0;line-height:1;}' +
    '.wz-nav-logo:hover{color:#ecfeff;text-decoration:none;}' +
    '.wz-nav-logo span{color:#22d3ee;}' +
    '.wz-nav-logo small{display:block;font-size:9px;font-weight:500;color:#64748b;' +
    'letter-spacing:.12em;text-transform:uppercase;margin-top:2px;}' +

    '.wz-nav-links{display:flex;align-items:center;gap:.25rem;margin-left:1.5rem;flex:1;}' +

    '.wz-nav-link{display:inline-flex;align-items:center;gap:.375rem;font-size:12px;' +
    'font-family:"Inter",system-ui,sans-serif;' +
    'font-weight:500;color:#94a3b8;padding:.375rem .75rem;border-radius:8px;' +
    'transition:color .15s,background .15s;text-decoration:none;}' +
    '.wz-nav-link svg{flex-shrink:0;}' +
    '.wz-nav-link:hover{color:#e2e8f0;background:rgba(255,255,255,.04);text-decoration:none;}' +

    '.wz-btn-nav{display:inline-flex;align-items:center;font-size:11.5px;font-weight:700;' +
    'font-family:"Inter",system-ui,sans-serif;' +
    'color:#020617;background:#22d3ee;padding:.375rem 1rem;border-radius:8px;' +
    'transition:background .15s;white-space:nowrap;flex-shrink:0;' +
    'margin-left:auto;text-decoration:none;}' +
    '.wz-btn-nav:hover{background:#67e8f9;text-decoration:none;}' +

    /* — Responsive — */
    '@media(max-width:480px){' +
    '.wz-nav-logo small{display:none;}' +
    '.wz-btn-nav{display:none;}' +
    '}';

  var styleEl = document.createElement('style');
  styleEl.textContent = css;
  document.head.appendChild(styleEl);

  /* ── Page courante ──────────────────────────────────────────────────────── */
  var path = window.location.pathname;
  var isBlogIndex = path === '/blog/' || path === '/blog/index.html';
  var isAgences   = path.startsWith('/agences/');

  /* ── Navbar ─────────────────────────────────────────────────────────────── */
  var links = '';
  if (!isBlogIndex) {
    links += '<a href="/blog/" class="wz-nav-link">' + ICON_BOOK + ' Blog</a>';
  }
  if (!isAgences) {
    links += '<a href="/agences/" class="wz-nav-link">' + ICON_BUILDING + ' Agences</a>';
  }

  var nav = document.createElement('nav');
  nav.className = 'wz-nav';
  nav.innerHTML =
    '<div class="wz-nav-inner">' +
      '<a href="https://wezea.net" class="wz-nav-logo">' +
        'We<span>zea</span>' +
        '<small>Security Scanner</small>' +
      '</a>' +
      '<div class="wz-nav-links">' + links + '</div>' +
      '<a href="https://wezea.net" class="wz-btn-nav">Scanner un domaine →</a>' +
    '</div>';

  /* Insertion synchrone au niveau du <script> appelant */
  var s = document.currentScript;
  if (s && s.parentNode) {
    s.parentNode.insertBefore(nav, s);
  } else {
    document.body.insertBefore(nav, document.body.firstChild);
  }

})();
