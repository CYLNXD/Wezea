// ─── App.tsx — Racine React ────────────────────────────────────────────────────
import { useState, useEffect } from 'react';
import { useLanguage } from './i18n/LanguageContext';
import Dashboard from './pages/Dashboard';
import LoginPage from './pages/LoginPage';
import HistoryPage from './pages/HistoryPage';
import AdminPage from './pages/AdminPage';
import ClientSpace from './pages/ClientSpace';
import ContactPage from './pages/ContactPage';
import LegalPage from './pages/LegalPage';
import PublicScanPage from './pages/PublicScanPage';
import CompliancePage from './pages/CompliancePage';
import type { LegalSection } from './pages/LegalPage';
import CookieBanner from './components/CookieBanner';
import { LanguageProvider } from './i18n/LanguageContext';
import { AuthProvider } from './contexts/AuthContext';
import { initClientId, } from './lib/api';
import { restoreConsent } from './lib/analytics';

type Page = 'dashboard' | 'login' | 'history' | 'admin' | 'clientspace' | 'contact' | 'legal' | 'public-scan' | 'compliance';
type ClientSpaceTab = 'overview' | 'monitoring' | 'apps' | 'history' | 'settings' | 'developer';
type SettingsSection = 'profile' | 'billing' | 'whitelabel' | 'danger';

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

// Composant interne pour les mises à jour de meta (doit être dans le LanguageProvider)
function MetaUpdater({ page }: { page: Page }) {
  const { lang } = useLanguage();
  useEffect(() => {
    if (page === 'compliance') {
      applyMeta(lang === 'en' ? COMPLIANCE_META_EN : COMPLIANCE_META);
    } else {
      applyMeta(DEFAULT_META);
    }
  }, [page, lang]);
  return null;
}

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

export default function App() {
  const [page, setPage]               = useState<Page>('dashboard');
  const [legalSection, setLegalSection] = useState<LegalSection>('mentions');
  const [loginMode, setLoginMode]       = useState<'login' | 'register'>('login');
  const [publicScanUuid, setPublicScanUuid]   = useState<string | null>(null);
  const [pendingScanUuid, setPendingScanUuid] = useState<string | null>(null);
  const [resetToken, setResetToken]     = useState<string | null>(null);
  const [csTab, setCsTab]                   = useState<ClientSpaceTab | undefined>(undefined);
  const [csSection, setCsSection]           = useState<SettingsSection | undefined>(undefined);

  const goClientSpace = (tab?: ClientSpaceTab, section?: SettingsSection) => {
    setCsTab(tab);
    setCsSection(section);
    setPage('clientspace');
  };

  // Initialise le cookie d'identification anonyme et restaure le consentement analytics
  useEffect(() => {
    initClientId();
    restoreConsent(); // réactive PostHog si l'utilisateur avait déjà accepté
  }, []);

  // Les meta OG/Twitter/canonical sont gérées par <MetaUpdater> (à l'intérieur du LanguageProvider)

  // Détecte les routes /r/{uuid} pour les rapports publics
  useEffect(() => {
    // Détecte la page de conformité NIS2/RGPD
    if (window.location.pathname === '/conformite-nis2') {
      setPage('compliance');
      return;
    }

    const path = window.location.pathname;
    const match = path.match(/^\/r\/([a-f0-9-]{36})$/i);
    if (match) {
      setPublicScanUuid(match[1]);
      setPage('public-scan');
      return;
    }

    // Gère le paramètre ?page=contact dans l'URL (lien depuis le PDF)
    const params = new URLSearchParams(window.location.search);
    const p = params.get('page');
    if (p === 'contact') {
      setPage('contact');
      window.history.replaceState({}, '', window.location.pathname);
    }
    const legal = params.get('legal') as LegalSection | null;
    if (legal) {
      setLegalSection(legal);
      setPage('legal');
      window.history.replaceState({}, '', window.location.pathname);
    }

    // Lien de réinitialisation de mot de passe — ?reset_token=xxx
    const rt = params.get('reset_token');
    if (rt) {
      setResetToken(rt);
      setPage('login');
      window.history.replaceState({}, '', window.location.pathname);
    }
  }, []);

  return (
    <LanguageProvider>
      <MetaUpdater page={page} />
      <AuthProvider>
        {/* Bandeau de consentement RGPD — s'affiche uniquement si aucun choix n'a été fait */}
        <CookieBanner
          onOpenCookies={() => { setLegalSection('cookies'); setPage('legal'); }}
        />

        {page === 'dashboard' && (
          <Dashboard
            onGoLogin={()        => { setLoginMode('login');    setPage('login'); }}
            onGoRegister={()     => { setLoginMode('register'); setPage('login'); }}
            onGoHistory={()      => setPage('history')}
            onGoAdmin={()        => setPage('admin')}
            onGoClientSpace={(tab?, section?) => goClientSpace(tab as ClientSpaceTab | undefined, section as SettingsSection | undefined)}
            onGoContact={()      => setPage('contact')}
            onGoLegal={(s)       => { setLegalSection((s ?? 'mentions') as LegalSection); setPage('legal'); }}
            onGoCompliance={()   => { window.history.pushState({}, '', '/conformite-nis2'); setPage('compliance'); }}
            initialScanUuid={pendingScanUuid}
            onScanUuidConsumed={() => setPendingScanUuid(null)}
          />
        )}
        {page === 'login' && (
          <LoginPage
            onBack={() => { setPage('dashboard'); setResetToken(null); }}
            initialMode={loginMode}
            resetToken={resetToken}
          />
        )}
        {page === 'history' && (
          <HistoryPage
            onBack={() => setPage('dashboard')}
            onLoadScan={(uuid) => { setPendingScanUuid(uuid); setPage('dashboard'); }}
            onGoAdmin={() => setPage('admin')}
            onGoClientSpace={() => goClientSpace()}
            onGoContact={() => setPage('contact')}
          />
        )}
        {page === 'admin' && (
          <AdminPage
            onBack={() => setPage('dashboard')}
            onGoHistory={() => setPage('history')}
            onGoClientSpace={() => goClientSpace()}
            onGoContact={() => setPage('contact')}
          />
        )}
        {page === 'clientspace' && (
          <ClientSpace
            onBack={() => setPage('dashboard')}
            onGoHistory={() => setPage('history')}
            onGoAdmin={() => setPage('admin')}
            onGoContact={() => setPage('contact')}
            initialTab={csTab}
            initialSettingsSection={csSection}
          />
        )}
        {page === 'contact' && (
          <ContactPage
            onBack={() => setPage('dashboard')}
            onGoClientSpace={() => goClientSpace()}
            onGoHistory={() => setPage('history')}
            onGoAdmin={() => setPage('admin')}
          />
        )}
        {page === 'legal' && (
          <LegalPage
            section={legalSection}
            onBack={() => setPage('dashboard')}
            onGoClientSpace={() => goClientSpace()}
            onGoHistory={() => setPage('history')}
            onGoAdmin={() => setPage('admin')}
            onGoContact={() => setPage('contact')}
          />
        )}
        {page === 'public-scan' && publicScanUuid && (
          <PublicScanPage
            uuid={publicScanUuid}
            onGoHome={() => {
              window.history.replaceState({}, '', '/');
              setPage('dashboard');
            }}
          />
        )}
        {page === 'compliance' && (
          <CompliancePage
            onGoBack={() => { window.history.replaceState({}, '', '/'); setPage('dashboard'); }}
            onGoRegister={() => { setLoginMode('register'); setPage('login'); }}
            onGoLogin={() => { setLoginMode('login'); setPage('login'); }}
          />
        )}
      </AuthProvider>
    </LanguageProvider>
  );
}
