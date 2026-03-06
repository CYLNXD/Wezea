// ─── App.tsx — Racine React ────────────────────────────────────────────────────
import { useState, useEffect } from 'react';
import Dashboard from './pages/Dashboard';
import LoginPage from './pages/LoginPage';
import HistoryPage from './pages/HistoryPage';
import AdminPage from './pages/AdminPage';
import ClientSpace from './pages/ClientSpace';
import ContactPage from './pages/ContactPage';
import LegalPage from './pages/LegalPage';
import PublicScanPage from './pages/PublicScanPage';
import type { LegalSection } from './pages/LegalPage';
import CookieBanner from './components/CookieBanner';
import { LanguageProvider } from './i18n/LanguageContext';
import { AuthProvider } from './contexts/AuthContext';
import { initClientId, } from './lib/api';
import { restoreConsent } from './lib/analytics';

type Page = 'dashboard' | 'login' | 'history' | 'admin' | 'clientspace' | 'contact' | 'legal' | 'public-scan';

export default function App() {
  const [page, setPage]               = useState<Page>('dashboard');
  const [legalSection, setLegalSection] = useState<LegalSection>('mentions');
  const [loginMode, setLoginMode]       = useState<'login' | 'register'>('login');
  const [publicScanUuid, setPublicScanUuid] = useState<string | null>(null);

  // Initialise le cookie d'identification anonyme et restaure le consentement analytics
  useEffect(() => {
    initClientId();
    restoreConsent(); // réactive PostHog si l'utilisateur avait déjà accepté
  }, []);

  // Détecte les routes /r/{uuid} pour les rapports publics
  useEffect(() => {
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
  }, []);

  return (
    <LanguageProvider>
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
            onGoClientSpace={()  => setPage('clientspace')}
            onGoContact={()      => setPage('contact')}
            onGoLegal={(s)       => { setLegalSection((s ?? 'mentions') as LegalSection); setPage('legal'); }}
          />
        )}
        {page === 'login' && (
          <LoginPage onBack={() => setPage('dashboard')} initialMode={loginMode} />
        )}
        {page === 'history' && (
          <HistoryPage
            onBack={() => setPage('dashboard')}
            onLoadScan={() => setPage('dashboard')}
            onGoAdmin={() => setPage('admin')}
            onGoClientSpace={() => setPage('clientspace')}
            onGoContact={() => setPage('contact')}
          />
        )}
        {page === 'admin' && (
          <AdminPage
            onBack={() => setPage('dashboard')}
            onGoHistory={() => setPage('history')}
            onGoClientSpace={() => setPage('clientspace')}
            onGoContact={() => setPage('contact')}
          />
        )}
        {page === 'clientspace' && (
          <ClientSpace
            onBack={() => setPage('dashboard')}
            onGoHistory={() => setPage('history')}
            onGoAdmin={() => setPage('admin')}
            onGoContact={() => setPage('contact')}
          />
        )}
        {page === 'contact' && (
          <ContactPage
            onBack={() => setPage('dashboard')}
            onGoClientSpace={() => setPage('clientspace')}
            onGoHistory={() => setPage('history')}
            onGoAdmin={() => setPage('admin')}
          />
        )}
        {page === 'legal' && (
          <LegalPage
            section={legalSection}
            onBack={() => setPage('dashboard')}
            onGoClientSpace={() => setPage('clientspace')}
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
      </AuthProvider>
    </LanguageProvider>
  );
}
