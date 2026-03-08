/**
 * analytics.ts — Wrapper PostHog pour le funnel de conversion Wezea
 *
 * PostHog est chargé via le snippet dans index.html (window.posthog).
 * Ce module fournit des helpers typés pour ne jamais appeler window.posthog
 * directement dans les composants.
 *
 * Funnel principal :
 *   $pageview → scan_started → scan_completed
 *     → register_cta_clicked → (inscription)
 *     → pricing_modal_opened → upgrade_plan_clicked
 *     → (checkout Stripe) → upgrade_confirmed (webhook)
 */

// ─── Déclaration du type global window.posthog ───────────────────────────────
declare global {
  interface Window {
    posthog?: {
      capture:    (event: string, properties?: Record<string, unknown>) => void;
      identify:   (distinctId: string, properties?: Record<string, unknown>) => void;
      reset:      () => void;
      get_distinct_id: () => string;
      opt_in_capturing:  () => void;
      opt_out_capturing: () => void;
      has_opted_in_capturing:  () => boolean;
      has_opted_out_capturing: () => boolean;
    };
  }
}

// ─── Consentement cookies ─────────────────────────────────────────────────────
const CONSENT_KEY = 'wezea_cookie_consent'; // 'accepted' | 'declined'

/** Active la collecte PostHog après consentement explicite */
export function analyticsOptIn(): void {
  try {
    localStorage.setItem(CONSENT_KEY, 'accepted');
    window.posthog?.opt_in_capturing();
  } catch { /* silencieux */ }
}

/** Désactive la collecte PostHog après refus explicite */
export function analyticsOptOut(): void {
  try {
    localStorage.setItem(CONSENT_KEY, 'declined');
    window.posthog?.opt_out_capturing();
  } catch { /* silencieux */ }
}

/** Retourne le statut de consentement stocké */
export function getConsentStatus(): 'accepted' | 'declined' | null {
  try {
    const v = localStorage.getItem(CONSENT_KEY);
    if (v === 'accepted' || v === 'declined') return v;
    return null;
  } catch { return null; }
}

/** Restaure le consentement au chargement de la page (appelé au démarrage de l'app) */
export function restoreConsent(): void {
  const status = getConsentStatus();
  if (status === 'accepted') {
    try { window.posthog?.opt_in_capturing(); } catch { /* silencieux */ }
  }
}

// ─── Helper interne ───────────────────────────────────────────────────────────
function ph(event: string, props?: Record<string, unknown>): void {
  try {
    window.posthog?.capture(event, props);
  } catch {
    // ne jamais crasher l'app pour un événement analytics
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Identité utilisateur
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Associe la session PostHog à un utilisateur identifié.
 * À appeler après login, register, et restauration de session.
 */
export function analyticsIdentify(
  userId: number,
  email: string,
  plan: string,
): void {
  try {
    window.posthog?.identify(String(userId), {
      email,
      plan,
      $email: email,   // propriété réservée PostHog pour l'affichage
    });
  } catch { /* silencieux */ }
}

/**
 * Réinitialise la session PostHog à la déconnexion.
 */
export function analyticsReset(): void {
  try {
    window.posthog?.reset();
  } catch { /* silencieux */ }
}

// ─────────────────────────────────────────────────────────────────────────────
// Funnel scan
// ─────────────────────────────────────────────────────────────────────────────

/** Utilisateur soumet le formulaire de scan */
export function captureScanStarted(domain: string): void {
  ph('scan_started', { domain });
}

/** Scan terminé avec succès */
export function captureScanCompleted(params: {
  domain: string;
  score: number;
  risk_level: string;
  findings_count: number;
  duration_ms?: number;
}): void {
  ph('scan_completed', params);
}

/** Scan échoué */
export function captureScanFailed(domain: string, error?: string): void {
  ph('scan_failed', { domain, error });
}

// ─────────────────────────────────────────────────────────────────────────────
// Funnel conversion
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Clic sur un bouton "créer un compte" ou "se connecter".
 * source : où se trouve le bouton dans l'interface.
 */
export type RegisterCtaSource =
  | 'nav'               // bouton de la navbar
  | 'scan_limit'        // quota atteint
  | 'pdf_gate'          // téléchargement PDF bloqué
  | 'hero'              // zone hero
  | 'results_banner'    // bannière après scan
  | 'maturity_widget'   // widget benchmark maturité
  | 'results_save'      // notice "résultats non sauvegardés"
  | 'sticky_bar'        // sticky bar bas d'écran post-scan
  | 'low_findings_gate'; // gate LOW findings dans l'onglet vulnérabilités

export function captureRegisterCtaClicked(source: RegisterCtaSource): void {
  ph('register_cta_clicked', { source });
}

/**
 * Ouverture de la modale de tarifs.
 */
export type PricingSource =
  | 'nav'
  | 'upgrade_banner'
  | 'scan_limit'
  | 'scan_limit_error'
  | 'agences_block'
  | 'pricing_section'
  | 'pro_features_section'
  | 'user_menu';

export function capturePricingModalOpened(source: PricingSource): void {
  ph('pricing_modal_opened', { source });
}

/**
 * Clic sur "Choisir ce plan" dans la modale de tarifs.
 * Déclenché avant la redirection Stripe.
 */
export function captureUpgradePlanClicked(plan: 'starter' | 'pro' | 'dev'): void {
  ph('upgrade_plan_clicked', { plan });
}

// ─────────────────────────────────────────────────────────────────────────────
// Actions produit
// ─────────────────────────────────────────────────────────────────────────────

/** Téléchargement d'un rapport PDF */
export function capturePdfDownloaded(domain: string, score: number, plan: string): void {
  ph('pdf_downloaded', { domain, score, plan });
}

/** Ajout d'un domaine au monitoring */
export function captureMonitoringDomainAdded(domain: string): void {
  ph('monitoring_domain_added', { domain });
}

/** Configuration marque blanche (Pro) */
export function captureWhiteLabelConfigured(): void {
  ph('white_label_configured', {});
}
