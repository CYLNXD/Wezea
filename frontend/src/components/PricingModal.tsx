import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Check, Zap, Shield, BarChart2, Key, Loader2, Code2, AppWindow } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { useLanguage } from '../i18n/LanguageContext';
import { captureUpgradePlanClicked } from '../lib/analytics';

interface Props {
  open:    boolean;
  onClose: () => void;
}

const FREE_FEATURES = [
  { fr: '5 scans / jour',             en: '5 scans / day' },
  { fr: 'Rapport PDF basique',       en: 'Basic PDF report' },
  { fr: 'Historique des scans',      en: 'Scan history' },
  { fr: 'Score de sécurité /100',    en: 'Security score /100' },
];

const STARTER_FEATURES = [
  { icon: Zap,       fr: 'Scans illimités',                       en: 'Unlimited scans' },
  { icon: BarChart2, fr: 'Rapport PDF avancé + recommandations',  en: 'Advanced PDF report + recommendations' },
  { icon: Shield,    fr: 'Monitoring continu + alertes email',    en: 'Continuous monitoring + email alerts' },
];

const PRO_FEATURES = [
  { icon: Zap,       fr: 'Tout le plan Starter',                  en: 'Everything in Starter' },
  { icon: Shield,    fr: 'Checks CVE / versions avancés',         en: 'Advanced CVE / version checks' },
  { icon: Shield,    fr: 'Rapports en marque blanche',            en: 'White-label reports' },
  { icon: Code2,     fr: 'Webhooks sortants (Zapier, Slack…)',    en: 'Outbound webhooks (Zapier, Slack…)' },
];

const DEV_FEATURES = [
  { icon: Zap,       fr: 'Tout le plan Pro',                                    en: 'Everything in Pro' },
  { icon: Key,       fr: 'Accès API (clé wsk_)',                                en: 'API access (wsk_ key)' },
  { icon: AppWindow, fr: 'Application Scanning (audit de vos apps web)',        en: 'Application Scanning (audit your web apps)' },
];

export default function PricingModal({ open, onClose }: Props) {
  const { user, refreshUser, getPortalUrl, upgradeToPlan } = useAuth();
  const { lang } = useLanguage();

  const [success,       setSuccess]       = useState(false);
  const [portalError,   setPortalError]   = useState('');
  const [loadingPlan,   setLoadingPlan]   = useState<string | null>(null);
  const [checkoutError, setCheckoutError] = useState('');

  // Fermeture par Escape
  const handleEscape = useCallback((e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); }, [onClose]);
  useEffect(() => {
    if (!open) return;
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [open, handleEscape]);

  // Détecter le retour depuis Stripe (?payment=success)
  useEffect(() => {
    if (!open) return;
    const params = new URLSearchParams(window.location.search);
    if (params.get('payment') === 'success') {
      setSuccess(true);
      window.history.replaceState({}, '', window.location.pathname);
      refreshUser();
    }
  }, [open]);

  const plan      = user?.plan ?? 'free';
  const isPaid    = plan !== 'free';
  const isStarter = plan === 'starter';
  const isPro     = plan === 'pro';
  const isDev     = plan === 'dev';

  const handlePortal = async () => {
    setPortalError('');
    try {
      const url = await getPortalUrl();
      window.location.href = url;
    } catch {
      setPortalError(
        lang === 'fr'
          ? 'Impossible d\'ouvrir le portail. Réessayez dans quelques secondes.'
          : 'Unable to open portal. Please try again.'
      );
    }
  };

  // ── Boutons ───────────────────────────────────────────────────────────────────
  const handleUpgrade = async (plan: 'starter' | 'pro' | 'dev') => {
    if (!user) return;
    setCheckoutError('');
    setLoadingPlan(plan);
    captureUpgradePlanClicked(plan);
    try {
      const url = await upgradeToPlan(plan);
      window.location.href = url;
    } catch {
      setCheckoutError(
        lang === 'fr'
          ? 'Erreur lors de la création du paiement. Réessayez dans quelques secondes.'
          : 'Error creating checkout. Please try again.'
      );
      setLoadingPlan(null);
    }
  };

  const UpgradeBtn = ({ plan }: { plan: 'starter' | 'pro' | 'dev' }) => (
    <button
      onClick={() => handleUpgrade(plan)}
      disabled={!!loadingPlan}
      className="w-full flex items-center justify-center gap-2 bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 disabled:cursor-not-allowed rounded-xl py-2.5 text-sm font-semibold text-slate-900 transition-colors"
    >
      {loadingPlan === plan
        ? <Loader2 size={15} className="animate-spin" />
        : <Zap size={15} />}
      {loadingPlan === plan
        ? (lang === 'fr' ? 'Redirection...' : 'Redirecting...')
        : (lang === 'fr' ? 'Choisir ce plan' : 'Choose this plan')}
    </button>
  );

  const ActiveBadge = () => (
    <div className="w-full flex items-center justify-center gap-2 bg-emerald-500/10 border border-emerald-500/30 rounded-xl py-2.5 text-sm font-medium text-emerald-400">
      <Check size={15} />
      {lang === 'fr' ? 'Plan actuel' : 'Current plan'}
    </div>
  );

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          {/* Backdrop */}
          <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />

          {/* Panel */}
          <motion.div
            className="relative z-10 w-full max-w-5xl sku-panel rounded-2xl overflow-hidden"
            initial={{ scale: 0.95, y: 20 }}
            animate={{ scale: 1, y: 0 }}
            exit={{ scale: 0.95, y: 20 }}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4" style={{ borderBottom: '1px solid var(--color-border)' }}>
              <div>
                <h2 className="text-lg font-semibold text-white">
                  {lang === 'fr' ? 'Choisissez votre plan' : 'Choose your plan'}
                </h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  {lang === 'fr'
                    ? 'Sans engagement — résiliable à tout moment depuis le portail Stripe'
                    : 'No commitment — cancel anytime from the Stripe portal'}
                </p>
              </div>
              <button onClick={onClose} className="text-slate-500 hover:text-slate-300 transition">
                <X size={20} />
              </button>
            </div>

            {/* Success banner */}
            {success && (
              <div className="mx-6 mt-4 flex items-center gap-3 bg-emerald-500/10 border border-emerald-500/30 rounded-xl px-4 py-3">
                <Check size={16} className="text-emerald-400 shrink-0" />
                <p className="text-sm text-emerald-400">
                  {lang === 'fr'
                    ? 'Paiement reçu ! Votre plan est actif. Si le changement n\'apparaît pas, reconnectez-vous.'
                    : 'Payment received! Your plan is now active. If the change is not visible, please sign out and back in.'}
                </p>
              </div>
            )}

            {/* Cards */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 p-6">

              {/* ── FREE ── */}
              <div className="sku-card rounded-xl p-5 flex flex-col">
                <div className="flex items-center justify-between mb-4">
                  <span className="text-sm font-medium text-slate-400">Free</span>
                  {plan === 'free' && (
                    <span className="text-xs bg-slate-700 text-slate-300 px-2 py-0.5 rounded-full">
                      {lang === 'fr' ? 'Plan actuel' : 'Current plan'}
                    </span>
                  )}
                </div>
                <div className="mb-4">
                  <span className="text-3xl font-bold text-white">0€</span>
                  <span className="text-slate-500 text-sm ml-1">/{lang === 'fr' ? 'mois' : 'month'}</span>
                </div>
                <ul className="space-y-2.5 flex-1">
                  {FREE_FEATURES.map((f, i) => (
                    <li key={i} className="flex items-center gap-2.5 text-sm text-slate-400">
                      <Check size={14} className="text-slate-600 shrink-0" />
                      {lang === 'fr' ? f.fr : f.en}
                    </li>
                  ))}
                </ul>
              </div>

              {/* ── STARTER ── */}
              <div className={`relative rounded-xl p-5 overflow-hidden flex flex-col ${
                isStarter
                  ? 'sku-card border-2 border-emerald-500/40'
                  : 'sku-card'
              }`}>
                {isStarter && <div className="absolute inset-0 bg-emerald-500/5 pointer-events-none" />}

                <div className="flex items-center justify-between mb-4 relative">
                  <span className="text-sm font-semibold text-slate-200">Starter</span>
                </div>

                <div className="mb-1 relative">
                  <span className="text-3xl font-bold text-white">9,90€</span>
                  <span className="text-slate-400 text-sm ml-1">/{lang === 'fr' ? 'mois' : 'month'}</span>
                </div>
                <p className="text-xs text-slate-500 mb-4">
                  {lang === 'fr' ? 'Idéal pour les PME' : 'Ideal for SMBs'}
                </p>

                <ul className="space-y-2.5 mb-6 flex-1">
                  {STARTER_FEATURES.map((f, i) => (
                    <li key={i} className="flex items-center gap-2.5 text-sm text-slate-300">
                      <f.icon size={14} className="text-slate-400 shrink-0" />
                      {lang === 'fr' ? f.fr : f.en}
                    </li>
                  ))}
                </ul>

                {isStarter
                  ? <ActiveBadge />
                  : user
                    ? <UpgradeBtn plan="starter" />
                    : (
                      <button
                        onClick={onClose}
                        className="w-full flex items-center justify-center gap-2 bg-emerald-500 hover:bg-emerald-400 rounded-xl py-2.5 text-sm font-semibold text-slate-900 transition-colors"
                      >
                        <Zap size={15} />
                        {lang === 'fr' ? 'Créer un compte' : 'Create an account'}
                      </button>
                    )
                }
              </div>

              {/* ── PRO ── */}
              <div className="relative sku-panel rounded-xl p-5 overflow-hidden flex flex-col" style={{ border: '2px solid rgba(34,211,238,0.35)', boxShadow: 'var(--shadow-panel), 0 0 30px rgba(34,211,238,0.06)' }}>
                <div className="absolute inset-0 bg-cyan-500/5 pointer-events-none" />

                <div className="flex items-center justify-between mb-4 relative">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-cyan-400">Pro</span>
                    <span className="text-xs bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 px-2 py-0.5 rounded-full font-medium">
                      {lang === 'fr' ? 'Recommandé' : 'Recommended'}
                    </span>
                  </div>
                </div>

                <div className="mb-1 relative">
                  <span className="text-3xl font-bold text-white">19,90€</span>
                  <span className="text-slate-400 text-sm ml-1">/{lang === 'fr' ? 'mois' : 'month'}</span>
                </div>
                <p className="text-xs text-slate-500 mb-4">
                  {lang === 'fr' ? 'Pour les intégrateurs & agences' : 'For integrators & agencies'}
                </p>

                <ul className="space-y-2.5 mb-6 flex-1">
                  {PRO_FEATURES.map((f, i) => (
                    <li key={i} className="flex items-center gap-2.5 text-sm text-slate-200">
                      <f.icon size={14} className="text-cyan-400 shrink-0" />
                      {lang === 'fr' ? f.fr : f.en}
                    </li>
                  ))}
                </ul>

                {isPro
                  ? <ActiveBadge />
                  : user
                    ? <UpgradeBtn plan="pro" />
                    : (
                      <button
                        onClick={onClose}
                        className="w-full flex items-center justify-center gap-2 bg-cyan-500 hover:bg-cyan-400 rounded-xl py-2.5 text-sm font-semibold text-slate-900 transition-colors"
                      >
                        <Zap size={15} />
                        {lang === 'fr' ? 'Créer un compte' : 'Create an account'}
                      </button>
                    )
                }
              </div>

              {/* ── DEV ── */}
              <div className="relative sku-panel rounded-xl p-5 overflow-hidden flex flex-col" style={{ border: '2px solid rgba(167,139,250,0.35)', boxShadow: 'var(--shadow-panel), 0 0 30px rgba(167,139,250,0.06)' }}>
                <div className="absolute inset-0 bg-violet-500/5 pointer-events-none" />

                <div className="flex items-center justify-between mb-4 relative">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-violet-400">Dev</span>
                    <span className="text-xs bg-violet-500/20 text-violet-400 border border-violet-500/30 px-2 py-0.5 rounded-full font-medium">
                      {lang === 'fr' ? 'Pour les devs' : 'For developers'}
                    </span>
                  </div>
                </div>

                <div className="mb-1 relative">
                  <span className="text-3xl font-bold text-white">29,90€</span>
                  <span className="text-slate-400 text-sm ml-1">/{lang === 'fr' ? 'mois' : 'month'}</span>
                </div>
                <p className="text-xs text-slate-500 mb-4">
                  {lang === 'fr' ? 'API + scan de vos propres apps' : 'API + scan your own apps'}
                </p>

                <ul className="space-y-2.5 mb-6 flex-1">
                  {DEV_FEATURES.map((f, i) => (
                    <li key={i} className="flex items-center gap-2.5 text-sm text-slate-200">
                      <f.icon size={14} className="text-violet-400 shrink-0" />
                      {lang === 'fr' ? f.fr : f.en}
                    </li>
                  ))}
                </ul>

                {isDev
                  ? <ActiveBadge />
                  : user
                    ? <UpgradeBtn plan="dev" />
                    : (
                      <button
                        onClick={onClose}
                        className="w-full flex items-center justify-center gap-2 bg-violet-500 hover:bg-violet-400 rounded-xl py-2.5 text-sm font-semibold text-white transition-colors"
                      >
                        <Zap size={15} />
                        {lang === 'fr' ? 'Créer un compte' : 'Create an account'}
                      </button>
                    )
                }
              </div>
            </div>

            {/* Erreur checkout */}
            {checkoutError && (
              <div className="mx-6 mb-2 text-center text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-2">
                {checkoutError}
              </div>
            )}

            {/* Footer — Gérer l'abonnement si plan payant */}
            <div className="px-6 pb-5 flex flex-col items-center gap-2">
              {isPaid && (
                <>
                  <button
                    onClick={handlePortal}
                    className="text-xs text-cyan-500 hover:text-cyan-400 transition-colors underline underline-offset-2 font-medium"
                  >
                    {lang === 'fr' ? '⚙️ Gérer mon abonnement (portail Stripe)' : '⚙️ Manage my subscription (Stripe portal)'}
                  </button>
                  {portalError && (
                    <p className="text-xs text-red-400">{portalError}</p>
                  )}
                </>
              )}
              <p className="text-xs text-slate-600">
                {lang === 'fr'
                  ? 'Questions ? Contactez-nous sur contact@wezea.net'
                  : 'Questions? Contact us at contact@wezea.net'}
              </p>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
