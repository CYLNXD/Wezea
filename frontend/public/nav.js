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
      var isActive = btn.getAttribute('data-lang') === lang;
      btn.setAttribute('data-active', isActive ? '1' : '0');
      btn.style.color     = isActive ? '#22d3ee' : '#475569';
      btn.style.background= isActive ? 'linear-gradient(180deg,#1e2d3d,#162433)' : 'transparent';
      btn.style.boxShadow = isActive ? '0 1px 0 rgba(255,255,255,0.06) inset' : 'none';
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

    '.wz-nav-inner{max-width:1152px;margin:0 auto;padding:0 1rem;height:52px;' +
    'display:flex;align-items:center;gap:.75rem;}' +

    /* — Logo — */
    '.wz-nav-logo{font-size:20px;font-weight:900;color:#fff;letter-spacing:-.03em;' +
    'font-family:-apple-system,"SF Pro Display","Inter",system-ui,sans-serif;' +
    'text-decoration:none;flex-shrink:0;line-height:1;}' +
    '.wz-nav-logo:hover{color:#ecfeff;text-decoration:none;}' +
    '.wz-nav-logo span{color:#22d3ee;}' +
    '.wz-nav-logo small{display:block;font-size:9px;font-weight:500;color:#64748b;' +
    'letter-spacing:.12em;text-transform:uppercase;margin-top:2px;}' +

    /* — Nav links (centre) — */
    '.wz-nav-links{display:flex;align-items:center;gap:.25rem;margin-left:1.25rem;flex:1;}' +

    '.wz-nav-link{display:inline-flex;align-items:center;gap:.375rem;font-size:12px;' +
    'font-family:"Inter",system-ui,sans-serif;' +
    'font-weight:500;color:#94a3b8;padding:.375rem .75rem;border-radius:8px;' +
    'transition:color .15s,background .15s;text-decoration:none;white-space:nowrap;}' +
    '.wz-nav-link svg{flex-shrink:0;}' +
    '.wz-nav-link:hover{color:#e2e8f0;background:rgba(255,255,255,.04);text-decoration:none;}' +

    /* — Right side — */
    '.wz-nav-right{display:flex;align-items:center;gap:.625rem;flex-shrink:0;margin-left:auto;}' +

    /* — Separator — */
    '.wz-nav-sep{width:1px;height:16px;background:rgba(255,255,255,.07);flex-shrink:0;}' +

    /* — Connexion button (ghost) — */
    '.wz-btn-login{display:inline-flex;align-items:center;font-size:12px;font-weight:500;' +
    'font-family:"Inter",system-ui,sans-serif;' +
    'color:#94a3b8;padding:.375rem .75rem;border-radius:8px;' +
    'border:1px solid rgba(255,255,255,.08);' +
    'transition:color .15s,background .15s;text-decoration:none;white-space:nowrap;}' +
    '.wz-btn-login:hover{color:#e2e8f0;background:rgba(255,255,255,.05);text-decoration:none;}' +

    /* — Sign up button (cyan) — */
    '.wz-btn-signup{display:inline-flex;align-items:center;font-size:12px;font-weight:700;' +
    'font-family:"Inter",system-ui,sans-serif;' +
    'color:#020617;background:#22d3ee;padding:.375rem .9rem;border-radius:8px;' +
    'transition:background .15s;white-space:nowrap;flex-shrink:0;' +
    'text-decoration:none;}' +
    '.wz-btn-signup:hover{background:#67e8f9;text-decoration:none;}' +

    /* — Language toggle (dark inset — same as React app) — */
    '.wz-lang-toggle{display:flex;overflow:hidden;border-radius:8px;' +
    'background:linear-gradient(180deg,#0f151e,#0b1018);' +
    'border:1px solid rgba(255,255,255,.07);' +
    'box-shadow:0 2px 5px rgba(0,0,0,.4) inset;' +
    'flex-shrink:0;}' +
    '.wz-lang-btn{font-size:11px;font-weight:700;letter-spacing:.04em;' +
    'font-family:"JetBrains Mono","Fira Code",monospace;' +
    'padding:.375rem .625rem;cursor:pointer;' +
    'border:none;background:transparent;transition:all .15s;line-height:1;' +
    'color:#475569;}' +
    '.wz-lang-btn[data-active="1"]{color:#22d3ee;' +
    'background:linear-gradient(180deg,#1e2d3d,#162433);' +
    'box-shadow:0 1px 0 rgba(255,255,255,.06) inset;}' +
    '.wz-lang-btn:hover:not([data-active="1"]){color:#e2e8f0;}' +

    /* — Responsive — */
    '@media(max-width:600px){' +
    '.wz-nav-logo small{display:none;}' +
    '.wz-btn-login{display:none;}' +
    '}' +
    '@media(max-width:480px){' +
    '.wz-btn-signup{display:none;}' +
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
  var loginLabel   = '<span class="lang-fr">Connexion</span><span class="lang-en">Sign in</span>';
  var signupLabel  = '<span class="lang-fr">Créer un compte</span><span class="lang-en">Sign up</span>';

  var links = '';
  if (!isBlogIndex) {
    links += '<a href="/blog/" class="wz-nav-link">' + ICON_BOOK + ' ' + blogLabel + '</a>';
  }
  if (!isAgences) {
    links += '<a href="/agences/" class="wz-nav-link">' + ICON_BUILDING + ' ' + agencesLabel + '</a>';
  }

  /* Active state inline (applied at render + updated by setLang) */
  function langBtnStyle(l) {
    return LANG === l
      ? 'color:#22d3ee;background:linear-gradient(180deg,#1e2d3d,#162433);box-shadow:0 1px 0 rgba(255,255,255,.06) inset;'
      : 'color:#475569;';
  }

  var langToggle =
    '<div class="wz-lang-toggle">' +
      '<button class="wz-lang-btn" data-lang="fr" data-active="' + (LANG==='fr'?'1':'0') + '" style="' + langBtnStyle('fr') + '">FR</button>' +
      '<button class="wz-lang-btn" data-lang="en" data-active="' + (LANG==='en'?'1':'0') + '" style="' + langBtnStyle('en') + '">EN</button>' +
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
      '<div class="wz-nav-right">' +
        langToggle +
        '<div class="wz-nav-sep"></div>' +
        '<a href="https://wezea.net" class="wz-btn-login">' + loginLabel + '</a>' +
        '<a href="https://wezea.net?register=1" class="wz-btn-signup">' + signupLabel + '</a>' +
      '</div>' +
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
