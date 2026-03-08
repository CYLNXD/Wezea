/* ── Wezea — Navbar + Footer partagés pour les pages statiques ──────────── */
(function () {
  /* ── Langue ──────────────────────────────────────────────────────────────── */
  var stored = localStorage.getItem('wz-lang');
  var auto   = (navigator.language || '').startsWith('en') ? 'en' : 'fr';
  var LANG   = stored || auto;
  document.documentElement.setAttribute('data-lang', LANG);

  function setLang(lang) {
    LANG = lang;
    localStorage.setItem('wz-lang', lang);
    document.documentElement.setAttribute('data-lang', lang);
    document.querySelectorAll('.wz-lang-btn').forEach(function(btn) {
      btn.setAttribute('data-active', btn.getAttribute('data-lang') === lang ? '1' : '0');
    });
    /* Meta title + description per-page override */
    var t = window.WZ_T;
    if (t && t[lang]) {
      if (t[lang].title)       document.title = t[lang].title;
      if (t[lang].description) { var m = document.querySelector('meta[name="description"]'); if(m) m.content = t[lang].description; }
      if (t[lang].og_title)    { var m = document.querySelector('meta[property="og:title"]'); if(m) m.content = t[lang].og_title; }
    }
  }

  /* Apply on load */
  setLang(LANG);

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

  /* ── CSS navbar + langue ────────────────────────────────────────────────── */
  var css =
    /* — Language visibility — */
    'html[data-lang="fr"] .lang-en{display:none!important;}' +
    'html[data-lang="en"] .lang-fr{display:none!important;}' +

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
    'text-decoration:none;}' +
    '.wz-btn-nav:hover{background:#67e8f9;text-decoration:none;}' +

    /* — Language toggle — */
    '.wz-lang-toggle{display:flex;align-items:center;gap:2px;' +
    'background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);' +
    'border-radius:8px;padding:2px;flex-shrink:0;margin-left:.5rem;}' +
    '.wz-lang-btn{font-size:11px;font-weight:600;letter-spacing:.04em;' +
    'font-family:"Inter",system-ui,sans-serif;' +
    'color:#64748b;padding:.25rem .5rem;border-radius:6px;cursor:pointer;' +
    'border:none;background:transparent;transition:all .15s;line-height:1;}' +
    '.wz-lang-btn[data-active="1"]{color:#020617;background:#22d3ee;}' +
    '.wz-lang-btn:hover:not([data-active="1"]){color:#e2e8f0;background:rgba(255,255,255,.06);}' +

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
  var blogLabel    = '<span class="lang-fr">Blog</span><span class="lang-en">Blog</span>';
  var agencesLabel = '<span class="lang-fr">Agences</span><span class="lang-en">Agencies</span>';
  var ctaLabel     = '<span class="lang-fr">Scanner un domaine →</span><span class="lang-en">Scan a domain →</span>';

  var links = '';
  if (!isBlogIndex) {
    links += '<a href="/blog/" class="wz-nav-link">' + ICON_BOOK + ' ' + blogLabel + '</a>';
  }
  if (!isAgences) {
    links += '<a href="/agences/" class="wz-nav-link">' + ICON_BUILDING + ' ' + agencesLabel + '</a>';
  }

  var langToggle =
    '<div class="wz-lang-toggle">' +
      '<button class="wz-lang-btn" data-lang="fr" data-active="' + (LANG==='fr'?'1':'0') + '">FR</button>' +
      '<button class="wz-lang-btn" data-lang="en" data-active="' + (LANG==='en'?'1':'0') + '">EN</button>' +
    '</div>';

  var nav = document.createElement('nav');
  nav.className = 'wz-nav';
  nav.innerHTML =
    '<div class="wz-nav-inner">' +
      '<a href="https://wezea.net" class="wz-nav-logo">' +
        'We<span>zea</span>' +
        '<small>Security Scanner</small>' +
      '</a>' +
      '<div class="wz-nav-links">' + links + '</div>' +
      langToggle +
      '<a href="https://wezea.net" class="wz-btn-nav">' + ctaLabel + '</a>' +
    '</div>';

  /* Insertion synchrone au niveau du <script> appelant */
  var s = document.currentScript;
  if (s && s.parentNode) {
    s.parentNode.insertBefore(nav, s);
  } else {
    document.body.insertBefore(nav, document.body.firstChild);
  }

  /* ── Lang toggle click ───────────────────────────────────────────────────── */
  nav.addEventListener('click', function(e) {
    var btn = e.target.closest('.wz-lang-btn');
    if (btn) setLang(btn.getAttribute('data-lang'));
  });

})();
