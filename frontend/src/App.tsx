// ─── App.tsx — Racine React ────────────────────────────────────────────────────
import { useState, useEffect } from 'react';
import Dashboard from './pages/Dashboard';
import LoginPage from './pages/LoginPage';
import HistoryPage from './pages/HistoryPage';
import AdminPage from './pages/AdminPage';
import ClientSpace from './pages/ClientSpace';
import ContactPage from './pages/ContactPage';
import LegalPage from './pages/LegalPage';
import type { LegalSection } from './pages/LegalPage';
import CookieBanner from './components/CookieBanner';
import { LanguageProvider } from './i18n/LanguageContext';
import { AuthProvider } from './contexts/AuthContext';
import { initClientId, } from './lib/api';
import { restoreConsent } from './lib/analytics';

type Page = 'dashboard' | 'login' | 'history' | 'admin' | 'clientspace' | 'contact' | 'legal';

export default function App() {
  const [page, setPage]               = useState<Page>('dashboard');
  const [legalSection, setLegalSection] = useState<LegalSection>('mentions');
  const [loginMode, setLoginMode]       = useState<'login' | 'register'>('login');

  // Initialise le cookie d'identification anonyme et restaure le consentement analytics
  useEffect(() => {
    initClientId();
    restoreConsent(); // réactive PostHog si l'utilisateur avait déjà accepté
  }, []);

  // Gère le paramètre ?page=contact dans l'URL (lien depuis le PDF)
  useEffect(() => {
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
        {/* Grille cyber globale — fixed, au-dessus du contenu (z-1), sous navbar/modals */}
        <div
          aria-hidden="true"
          style={{
            position: 'fixed',
            inset: 0,
            pointerEvents: 'none',
            zIndex: 1,
            backgroundImage:
              'linear-gradient(rgba(34,211,238,1) 1px, transparent 1px),' +
              'linear-gradient(90deg, rgba(34,211,238,1) 1px, transparent 1px)',
            backgroundSize: '48px 48px',
            opacity: 0.03,
          }}
        />

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
      </AuthProvider>
    </LanguageProvider>
  );
}
