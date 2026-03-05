// ─── Contexte de langue FR / EN ───────────────────────────────────────────────
import { createContext, useContext, useState, ReactNode } from 'react';
import { translations, Lang, TranslationKey } from './translations';

// ─────────────────────────────────────────────────────────────────────────────

interface LanguageContextValue {
  lang:      Lang;
  setLang:   (l: Lang) => void;
  t:         (key: TranslationKey, vars?: Record<string, string | number>) => string;
}

const LanguageContext = createContext<LanguageContextValue | null>(null);

// ─────────────────────────────────────────────────────────────────────────────

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>(() => {
    // Détecter la langue du navigateur au premier chargement
    const saved = localStorage.getItem('cyberhealth_lang') as Lang | null;
    if (saved === 'fr' || saved === 'en') return saved;
    const browser = navigator.language.startsWith('fr') ? 'fr' : 'en';
    return browser;
  });

  const handleSetLang = (l: Lang) => {
    setLang(l);
    localStorage.setItem('cyberhealth_lang', l);
  };

  // Fonction de traduction avec interpolation simple : {variable}
  const t = (key: TranslationKey, vars?: Record<string, string | number>): string => {
    const raw = (translations[lang] as Record<string, string>)[key]
             ?? (translations.fr  as Record<string, string>)[key]
             ?? key;
    if (!vars) return raw;
    return raw.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? `{${k}}`));
  };

  return (
    <LanguageContext.Provider value={{ lang, setLang: handleSetLang, t }}>
      {children}
    </LanguageContext.Provider>
  );
}

// ─────────────────────────────────────────────────────────────────────────────

export function useLanguage() {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error('useLanguage must be used inside <LanguageProvider>');
  return ctx;
}
