// ─── App.tsx — Racine React ────────────────────────────────────────────────────
import { useEffect, lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { useLanguage } from './i18n/LanguageContext';
import Dashboard from './pages/Dashboard';

// ── Lazy-loaded pages (code splitting) ──────────────────────────────────────────
const LoginPage      = lazy(() => import('./pages/LoginPage'));
const HistoryPage    = lazy(() => import('./pages/HistoryPage'));
const AdminPage      = lazy(() => import('./pages/AdminPage'));
const ClientSpace    = lazy(() => import('./pages/ClientSpace'));
const ContactPage    = lazy(() => import('./pages/ContactPage'));
const LegalPage      = lazy(() => import('./pages/LegalPage'));
const PublicScanPage = lazy(() => import('./pages/PublicScanPage'));
const CompliancePage = lazy(() => import('./pages/CompliancePage'));
const PartnerPage    = lazy(() => import('./pages/PartnerPage'));
// Blog pages not used — static HTML blog in /public/blog/
import CookieBanner from './components/CookieBanner';
import ErrorBoundary from './components/ErrorBoundary';
import { LanguageProvider } from './i18n/LanguageContext';
import { AuthProvider } from './contexts/AuthContext';
import { initClientId } from './lib/api';
import { restoreConsent } from './lib/analytics';

// ── SEO — meta tags par page ──────────────────────────────────────────────────
const DEFAULT_META = {
  title:      'Wezea — Audit de sécurité web en 60 secondes | DAST · NIS2 · Secret Scanner',
  desc:       "40+ vérifications de sécurité : SSL/TLS, DNS, DAST actif, Secret Scanner, conformité NIS2 & RGPD. Score /100 avec plan d'action priorisé et rapport PDF. Sans installation.",
  keywords:   'audit sécurité web, scanner domaine, DAST, Secret Scanner, conformité NIS2, audit RGPD, SPF DMARC SSL, CVE, cybersécurité PME, agence web, MSP, rapport sécurité PDF',
  canonical:  'https://wezea.net',
  ogTitle:    'Wezea — Audit de sécurité web complet en 60 secondes',
  ogDesc:     "40+ vérifications : SSL, DNS, DAST actif, Secret Scanner, conformité NIS2 & RGPD. Score /100 et plan d'action. Sans installation, sans accès serveur.",
  ogUrl:      'https://wezea.net',
  twTitle:    'Wezea — Audit de sécurité web en 60 secondes',
  twDesc:     '40+ vérifications : DAST, Secret Scanner, NIS2, RGPD, SSL, DNS, CVE. Score /100 + rapport PDF. Gratuit pour les PME et agences.',
} as const;

const COMPLIANCE_META = {
  title:      'Conformité NIS2 & RGPD — Diagnostic gratuit en 60s | Wezea',
  desc:       'Vérifiez gratuitement la conformité de votre infrastructure aux directives NIS2 (art. 21) et RGPD (art. 25 & 32). 12 critères techniques analysés en 60 secondes. Sans installation.',
  keywords:   'conformité NIS2, RGPD article 32, directive NIS2 PME, audit conformité cybersécurité, NIS2 checklist, RGPD sécurité traitement, diagnostic NIS2 gratuit, vérification NIS2',
  canonical:  'https://wezea.net/conformite-nis2',
  ogTitle:    'Conformité NIS2 & RGPD — Diagnostic gratuit en 60s | Wezea',
  ogDesc:     '12 critères NIS2 (art. 21) et RGPD (art. 25 & 32) vérifiés en 60 secondes. Diagnostic gratuit de votre conformité réglementaire — sans installation, sans accès serveur.',
  ogUrl:      'https://wezea.net/conformite-nis2',
  twTitle:    'Conformité NIS2 & RGPD — Diagnostic gratuit | Wezea',
  twDesc:     '12 critères réglementaires NIS2 et RGPD analysés en 60 secondes. Gratuit, sans installation, sans accès serveur.',
} as const;

const COMPLIANCE_META_EN = {
  title:      'NIS2 & GDPR Compliance — Free diagnosis in 60s | Wezea',
  desc:       'Check your infrastructure compliance with NIS2 (art. 21) and GDPR (art. 25 & 32) for free. 12 technical criteria analysed in 60 seconds. No installation required.',
  keywords:   'NIS2 compliance, GDPR article 32, NIS2 directive SME, cybersecurity compliance audit, NIS2 checklist, GDPR security, free NIS2 diagnosis, NIS2 verification',
  canonical:  'https://wezea.net/conformite-nis2',
  ogTitle:    'NIS2 & GDPR Compliance — Free diagnosis in 60s | Wezea',
  ogDesc:     '12 NIS2 (art. 21) and GDPR (art. 25 & 32) criteria checked in 60 seconds. Free regulatory compliance diagnosis — no installation, no server access.',
  ogUrl:      'https://wezea.net/conformite-nis2',
  twTitle:    'NIS2 & GDPR Compliance — Free diagnosis | Wezea',
  twDesc:     '12 NIS2 and GDPR criteria analysed in 60 seconds. Free, no installation, no server access.',
} as const;

interface MetaConfig {
  title: string; desc: string; keywords: string; canonical: string;
  ogTitle: string; ogDesc: string; ogUrl: string;
  twTitle: string; twDesc: string;
}

function applyMeta(m: MetaConfig): void {
  document.title = m.title;
  const set = (sel: string, attr: string, val: string) =>
    document.querySelector(sel)?.setAttribute(attr, val);
  set('meta[name="description"]',         'content', m.desc);
  set('meta[name="keywords"]',            'content', m.keywords);
  set('link[rel="canonical"]',            'href',    m.canonical);
  set('meta[property="og:title"]',        'content', m.ogTitle);
  set('meta[property="og:description"]',  'content', m.ogDesc);
  set('meta[property="og:url"]',          'content', m.ogUrl);
  set('meta[name="twitter:title"]',       'content', m.twTitle);
  set('meta[name="twitter:description"]', 'content', m.twDesc);
}

// Composant interne pour les mises à jour de meta (doit être dans le LanguageProvider + Router)
function MetaUpdater() {
  const { lang } = useLanguage();
  const { pathname } = useLocation();
  useEffect(() => {
    if (pathname === '/conformite-nis2') {
      applyMeta(lang === 'en' ? COMPLIANCE_META_EN : COMPLIANCE_META);
    } else {
      applyMeta(DEFAULT_META);
    }
  }, [pathname, lang]);
  return null;
}

// ── Gère les legacy query params et les redirige vers les bonnes routes ──────
function LegacyRedirects() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { pathname } = useLocation();

  useEffect(() => {
    // Seulement sur la racine — ne pas interférer avec les autres routes
    if (pathname !== '/') return;

    const page = searchParams.get('page');
    if (page === 'contact') {
      navigate('/contact', { replace: true });
      return;
    }

    const legal = searchParams.get('legal');
    if (legal) {
      navigate(`/mentions-legales/${legal}`, { replace: true });
      return;
    }

    // Reset token — redirige vers /login avec le token en query
    const rt = searchParams.get('reset_token');
    if (rt) {
      navigate(`/login?reset_token=${encodeURIComponent(rt)}`, { replace: true });
      return;
    }
  }, [pathname, searchParams, navigate]);

  return null;
}

// ── Capture le code referral depuis ?ref=wza_XXXX ────────────────────────────
function ReferralCapture() {
  const [searchParams] = useSearchParams();

  useEffect(() => {
    const ref = searchParams.get('ref');
    if (ref && /^wza_[A-Z0-9]{6}$/i.test(ref)) {
      const code = ref.toUpperCase();
      localStorage.setItem('wezea_referral_code', code);
    }
  }, [searchParams]);

  return null;
}

// ── Scroll to top on route change ────────────────────────────────────────────
function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return null;
}

function PageSpinner() {
  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="w-8 h-8 border-2 border-cyan-400/30 border-t-cyan-400 rounded-full animate-spin" />
    </div>
  );
}

export default function App() {
  // Initialise le cookie d'identification anonyme et restaure le consentement analytics
  useEffect(() => {
    initClientId();
    restoreConsent(); // réactive PostHog si l'utilisateur avait déjà accepté
  }, []);

  return (
    <ErrorBoundary>
    <LanguageProvider>
    <BrowserRouter>
      <MetaUpdater />
      <LegacyRedirects />
      <ReferralCapture />
      <ScrollToTop />
      <AuthProvider>
        {/* Bandeau de consentement RGPD — s'affiche uniquement si aucun choix n'a été fait */}
        <CookieBanner />

        <Suspense fallback={<PageSpinner />}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/login" element={<LoginPage initialMode="login" />} />
            <Route path="/register" element={<LoginPage initialMode="register" />} />
            <Route path="/history" element={<HistoryPage />} />
            <Route path="/admin" element={<AdminPage />} />
            <Route path="/espace-client" element={<ClientSpace />} />
            <Route path="/espace-client/:tab" element={<ClientSpace />} />
            <Route path="/contact" element={<ContactPage />} />
            <Route path="/mentions-legales" element={<LegalPage />} />
            <Route path="/mentions-legales/:section" element={<LegalPage />} />
            <Route path="/r/:uuid" element={<PublicScanPage />} />
            <Route path="/conformite-nis2" element={<CompliancePage />} />
            <Route path="/partenaires" element={<PartnerPage />} />
            {/* Blog is served as static HTML from /blog/index.html — no React route needed */}
            {/* Fallback — redirect to dashboard */}
            <Route path="*" element={<Dashboard />} />
          </Routes>
        </Suspense>
      </AuthProvider>
    </BrowserRouter>
    </LanguageProvider>
    </ErrorBoundary>
  );
}
