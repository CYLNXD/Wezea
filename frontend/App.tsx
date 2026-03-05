// ─── App.tsx — Racine React ────────────────────────────────────────────────────
import { useState } from 'react';
import Dashboard from './pages/Dashboard';
import LoginPage from './pages/LoginPage';
import HistoryPage from './pages/HistoryPage';
import { LanguageProvider } from './i18n/LanguageContext';
import { AuthProvider } from './contexts/AuthContext';

type Page = 'dashboard' | 'login' | 'history';

export default function App() {
  const [page, setPage] = useState<Page>('dashboard');

  return (
    <LanguageProvider>
      <AuthProvider>
        {page === 'dashboard' && (
          <Dashboard
            onGoLogin={()   => setPage('login')}
            onGoHistory={() => setPage('history')}
          />
        )}
        {page === 'login' && (
          <LoginPage onBack={() => setPage('dashboard')} />
        )}
        {page === 'history' && (
          <HistoryPage
            onBack={() => setPage('dashboard')}
            onLoadScan={() => setPage('dashboard')}
          />
        )}
      </AuthProvider>
    </LanguageProvider>
  );
}
