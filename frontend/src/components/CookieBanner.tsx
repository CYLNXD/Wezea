// ─── CookieBanner.tsx — Bandeau de consentement RGPD ─────────────────────────
import { useState, useEffect } from 'react';
import { analyticsOptIn, analyticsOptOut, getConsentStatus } from '../lib/analytics';

interface CookieBannerProps {
  /** Callback pour ouvrir la page politique des cookies */
  onOpenCookies?: () => void;
}

export default function CookieBanner({ onOpenCookies }: CookieBannerProps) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    // N'afficher le bandeau que si aucun consentement n'a été donné
    if (getConsentStatus() === null) {
      // Petit délai pour ne pas gêner le chargement initial
      const t = setTimeout(() => setVisible(true), 800);
      return () => clearTimeout(t);
    }
  }, []);

  if (!visible) return null;

  function handleAccept() {
    analyticsOptIn();
    setVisible(false);
  }

  function handleDecline() {
    analyticsOptOut();
    setVisible(false);
  }

  return (
    <div
      role="dialog"
      aria-label="Consentement cookies"
      style={{
        position: 'fixed',
        bottom: 0,
        left: 0,
        right: 0,
        zIndex: 9999,
        background: 'rgba(2, 6, 23, 0.97)',
        borderTop: '1px solid rgba(34, 211, 238, 0.2)',
        backdropFilter: 'blur(12px)',
        WebkitBackdropFilter: 'blur(12px)',
        padding: '1rem 1.5rem',
        boxShadow: '0 -4px 32px rgba(0, 0, 0, 0.5)',
      }}
    >
      <div style={{
        maxWidth: 1152,
        margin: '0 auto',
        display: 'flex',
        alignItems: 'center',
        gap: '1.25rem',
        flexWrap: 'wrap',
      }}>
        {/* Icône cookie */}
        <span style={{ fontSize: 22, flexShrink: 0 }}>🍪</span>

        {/* Texte */}
        <p style={{
          flex: 1,
          minWidth: 200,
          margin: 0,
          fontSize: 13,
          color: '#94a3b8',
          lineHeight: 1.5,
        }}>
          Wezea utilise des cookies analytiques (PostHog) pour améliorer l'expérience et mesurer l'usage du scanner.
          Ces données restent anonymisées et ne sont jamais revendues.{' '}
          <button
            onClick={onOpenCookies}
            style={{
              background: 'none',
              border: 'none',
              padding: 0,
              cursor: 'pointer',
              color: '#22d3ee',
              fontSize: 13,
              textDecoration: 'underline',
              textUnderlineOffset: 2,
            }}
          >
            En savoir plus
          </button>
        </p>

        {/* Boutons */}
        <div style={{ display: 'flex', gap: '.625rem', flexShrink: 0 }}>
          <button
            onClick={handleDecline}
            style={{
              padding: '.4rem .9rem',
              borderRadius: 8,
              border: '1px solid rgba(148, 163, 184, 0.25)',
              background: 'transparent',
              color: '#64748b',
              fontSize: 12,
              fontWeight: 600,
              cursor: 'pointer',
              transition: 'color .15s, border-color .15s',
              whiteSpace: 'nowrap',
            }}
            onMouseEnter={e => {
              (e.currentTarget as HTMLButtonElement).style.color = '#94a3b8';
              (e.currentTarget as HTMLButtonElement).style.borderColor = 'rgba(148, 163, 184, 0.5)';
            }}
            onMouseLeave={e => {
              (e.currentTarget as HTMLButtonElement).style.color = '#64748b';
              (e.currentTarget as HTMLButtonElement).style.borderColor = 'rgba(148, 163, 184, 0.25)';
            }}
          >
            Refuser
          </button>
          <button
            onClick={handleAccept}
            style={{
              padding: '.4rem 1.1rem',
              borderRadius: 8,
              border: 'none',
              background: '#22d3ee',
              color: '#020617',
              fontSize: 12,
              fontWeight: 700,
              cursor: 'pointer',
              transition: 'background .15s',
              whiteSpace: 'nowrap',
            }}
            onMouseEnter={e => {
              (e.currentTarget as HTMLButtonElement).style.background = '#67e8f9';
            }}
            onMouseLeave={e => {
              (e.currentTarget as HTMLButtonElement).style.background = '#22d3ee';
            }}
          >
            Accepter
          </button>
        </div>
      </div>
    </div>
  );
}
