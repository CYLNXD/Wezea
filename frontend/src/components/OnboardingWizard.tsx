// ─── OnboardingWizard.tsx — Modal de bienvenue post-inscription ───────────────
//
// Affiché une seule fois après l'inscription.
// Flag localStorage : wezea_onboarding_done_{userId}
// Étapes : Bienvenue → Scanner votre domaine → Prochaines étapes
//
import { useState, ReactNode, FormEvent } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  Shield, Globe, Star, ArrowRight, X, CheckCircle,
  Bell, Zap, FileText, Lock,
} from 'lucide-react';
import type { AuthUser } from '../contexts/AuthContext';

// ─── SkuIcon ──────────────────────────────────────────────────────────────────
function SkuIcon({ children, color, size = 44 }: { children: ReactNode; color: string; size?: number }) {
  const r = Math.round(size * 0.28);
  return (
    <div
      className="shrink-0 flex items-center justify-center relative overflow-hidden"
      style={{
        width: size, height: size, borderRadius: r,
        background: `linear-gradient(150deg, ${color}30 0%, ${color}0d 100%)`,
        border: `1px solid ${color}40`,
        boxShadow: `0 4px 16px ${color}22, 0 1px 3px rgba(0,0,0,0.4), inset 0 1px 0 ${color}30, inset 0 -1px 0 rgba(0,0,0,0.3)`,
      }}
    >
      <div
        className="absolute inset-0 pointer-events-none"
        style={{ borderRadius: r, background: 'linear-gradient(180deg,rgba(255,255,255,0.07) 0%,transparent 50%)' }}
      />
      {children}
    </div>
  );
}

// ─── StepDot ──────────────────────────────────────────────────────────────────
function StepDots({ total, current }: { total: number; current: number }) {
  return (
    <div className="flex items-center gap-2 justify-center">
      {Array.from({ length: total }).map((_, i) => (
        <div
          key={i}
          style={{
            width: i === current ? 20 : 6,
            height: 6,
            borderRadius: 3,
            background: i === current ? '#22d3ee' : 'rgba(255,255,255,0.15)',
            transition: 'all 0.3s ease',
          }}
        />
      ))}
    </div>
  );
}

// ─── Props ────────────────────────────────────────────────────────────────────
interface Props {
  user: AuthUser;
  /** Appelé quand l'utilisateur lance un scan depuis le wizard */
  onStartScan: (domain: string) => void;
  /** Appelé quand l'utilisateur clique "Voir mon espace" */
  onGoClientSpace: (tab?: string) => void;
  /** Ferme le wizard sans action */
  onClose: () => void;
}

// ─── Composant principal ──────────────────────────────────────────────────────
export default function OnboardingWizard({ user, onStartScan, onGoClientSpace, onClose }: Props) {
  const [step, setStep] = useState(0);
  const [domain, setDomain] = useState('');
  const [domainError, setDomainError] = useState('');

  const firstName = user.first_name || user.email.split('@')[0];

  // Validation rapide du domaine
  function validateDomain(d: string): boolean {
    const clean = d.trim().replace(/^https?:\/\//i, '').replace(/^www\./i, '').split('/')[0];
    return /^[a-zA-Z0-9][a-zA-Z0-9\-]*(\.[a-zA-Z]{2,})+$/.test(clean);
  }

  function handleScan(e: FormEvent) {
    e.preventDefault();
    setDomainError('');
    const clean = domain.trim().replace(/^https?:\/\//i, '').replace(/^www\./i, '').split('/')[0];
    if (!clean || !validateDomain(clean)) {
      setDomainError('Entrez un nom de domaine valide (ex: mon-site.fr)');
      return;
    }
    onStartScan(clean);
    onClose();
  }

  const STEPS = [
    {
      key: 'welcome',
      render: () => (
        <motion.div
          key="step-welcome"
          initial={{ opacity: 0, x: 40 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -40 }}
          transition={{ duration: 0.3 }}
          className="flex flex-col items-center text-center gap-6"
        >
          {/* Icône hero */}
          <SkuIcon color="#22d3ee" size={72}>
            <Shield size={36} className="text-cyan-300" />
          </SkuIcon>

          {/* Titre */}
          <div>
            <h2 className="text-2xl font-bold text-white mb-2" style={{ fontFamily: 'var(--font-display)' }}>
              Bienvenue, {firstName} 👋
            </h2>
            <p className="text-slate-400 text-sm leading-relaxed max-w-sm mx-auto">
              CyberHealth Scanner analyse la sécurité de vos domaines et vous aide à corriger les vulnérabilités avant qu'elles ne soient exploitées.
            </p>
          </div>

          {/* 3 cartes de fonctionnalités */}
          <div className="w-full grid grid-cols-1 gap-3 text-left">
            {[
              { icon: Globe, color: '#22d3ee', title: 'Analyse complète', desc: 'SSL, DNS, ports, technologies — un score de sécurité en secondes.' },
              { icon: Bell, color: '#a78bfa', title: 'Surveillance continue', desc: 'Soyez alerté dès qu\'une anomalie est détectée sur vos domaines.' },
              { icon: FileText, color: '#4ade80', title: 'Rapport PDF expert', desc: 'Un rapport professionnel pour vos clients ou votre équipe IT.' },
            ].map(({ icon: Icon, color, title, desc }) => (
              <div
                key={title}
                className="flex items-start gap-3 p-3 rounded-lg"
                style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}
              >
                <SkuIcon color={color} size={32}>
                  <Icon size={16} style={{ color }} />
                </SkuIcon>
                <div>
                  <div className="text-sm font-semibold text-white">{title}</div>
                  <div className="text-xs text-slate-400 leading-snug mt-0.5">{desc}</div>
                </div>
              </div>
            ))}
          </div>

          {/* CTA */}
          <button
            onClick={() => setStep(1)}
            className="sku-btn-primary w-full flex items-center justify-center gap-2"
            style={{ padding: '12px 24px', fontSize: '0.9rem' }}
          >
            <Zap size={16} />
            Commencer — scanner mon domaine
            <ArrowRight size={16} />
          </button>
          <button
            onClick={onClose}
            className="text-xs text-slate-500 hover:text-slate-400 transition-colors"
          >
            Passer l'introduction
          </button>
        </motion.div>
      ),
    },
    {
      key: 'scan',
      render: () => (
        <motion.div
          key="step-scan"
          initial={{ opacity: 0, x: 40 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -40 }}
          transition={{ duration: 0.3 }}
          className="flex flex-col items-center text-center gap-6"
        >
          <SkuIcon color="#22d3ee" size={60}>
            <Globe size={28} className="text-cyan-300" />
          </SkuIcon>

          <div>
            <h2 className="text-xl font-bold text-white mb-2" style={{ fontFamily: 'var(--font-display)' }}>
              Scannez votre premier domaine
            </h2>
            <p className="text-slate-400 text-sm leading-relaxed">
              Entrez le domaine que vous souhaitez analyser. L'analyse prend environ 15 secondes.
            </p>
          </div>

          <form onSubmit={handleScan} className="w-full flex flex-col gap-3">
            <div className="w-full">
              <input
                type="text"
                value={domain}
                onChange={e => { setDomain(e.target.value); setDomainError(''); }}
                placeholder="mon-site.fr"
                autoFocus
                className="sku-inset w-full px-4 py-3 rounded-lg text-white text-sm font-mono placeholder-slate-600 outline-none focus:ring-1 focus:ring-cyan-500/40"
              />
              {domainError && (
                <p className="text-xs text-red-400 mt-1.5 text-left">{domainError}</p>
              )}
            </div>

            <button
              type="submit"
              className="sku-btn-primary w-full flex items-center justify-center gap-2"
              style={{ padding: '12px 24px', fontSize: '0.9rem' }}
            >
              <Shield size={16} />
              Lancer l'analyse
            </button>
          </form>

          {/* Exemples cliquables */}
          <div className="flex flex-col items-center gap-1">
            <span className="text-xs text-slate-600">Exemples :</span>
            <div className="flex gap-2 flex-wrap justify-center">
              {['exemple.fr', 'mon-shop.com', 'startup.io'].map(ex => (
                <button
                  key={ex}
                  onClick={() => setDomain(ex)}
                  className="text-xs px-2 py-0.5 rounded text-slate-400 hover:text-cyan-400 transition-colors"
                  style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)' }}
                >
                  {ex}
                </button>
              ))}
            </div>
          </div>

          {/* Lien vers étape suivante */}
          <button
            onClick={() => setStep(2)}
            className="text-xs text-slate-500 hover:text-slate-400 transition-colors"
          >
            Je veux d'abord explorer les fonctionnalités →
          </button>
        </motion.div>
      ),
    },
    {
      key: 'next',
      render: () => (
        <motion.div
          key="step-next"
          initial={{ opacity: 0, x: 40 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -40 }}
          transition={{ duration: 0.3 }}
          className="flex flex-col items-center text-center gap-6"
        >
          <SkuIcon color="#4ade80" size={60}>
            <CheckCircle size={28} className="text-green-300" />
          </SkuIcon>

          <div>
            <h2 className="text-xl font-bold text-white mb-2" style={{ fontFamily: 'var(--font-display)' }}>
              Vous êtes prêt !
            </h2>
            <p className="text-slate-400 text-sm leading-relaxed">
              Votre espace vous attend. Voici ce que vous pouvez faire dès maintenant.
            </p>
          </div>

          <div className="w-full grid grid-cols-1 gap-3 text-left">
            {[
              {
                icon: Globe, color: '#22d3ee',
                title: 'Scanner un domaine',
                desc: 'Depuis le tableau de bord, entrez n\'importe quel domaine pour obtenir votre score.',
                action: () => { onClose(); },
              },
              {
                icon: Bell, color: '#a78bfa',
                title: 'Activer la surveillance',
                desc: 'Recevez des alertes email en cas de changement sur vos domaines.',
                action: () => { onGoClientSpace('monitoring'); onClose(); },
              },
              {
                icon: Star, color: '#fbbf24',
                title: 'Voir les plans',
                desc: 'Débloquez les rapports PDF, l\'API et la surveillance illimitée.',
                action: () => { onGoClientSpace('billing'); onClose(); },
              },
            ].map(({ icon: Icon, color, title, desc, action }) => (
              <button
                key={title}
                onClick={action}
                className="flex items-start gap-3 p-3 rounded-lg text-left w-full transition-all group"
                style={{
                  background: 'rgba(255,255,255,0.03)',
                  border: '1px solid rgba(255,255,255,0.06)',
                }}
                onMouseEnter={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.06)')}
                onMouseLeave={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.03)')}
              >
                <SkuIcon color={color} size={32}>
                  <Icon size={16} style={{ color }} />
                </SkuIcon>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold text-white">{title}</div>
                  <div className="text-xs text-slate-400 leading-snug mt-0.5">{desc}</div>
                </div>
                <ArrowRight size={14} className="text-slate-600 group-hover:text-slate-400 transition-colors shrink-0 mt-1" />
              </button>
            ))}
          </div>

          <button
            onClick={onClose}
            className="sku-btn-ghost w-full flex items-center justify-center gap-2"
            style={{ padding: '10px 24px', fontSize: '0.85rem' }}
          >
            <Lock size={14} />
            Fermer et explorer
          </button>
        </motion.div>
      ),
    },
  ];

  return (
    // Overlay
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.2 }}
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(8px)' }}
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      {/* Panel */}
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 16 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 16 }}
        transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
        className="sku-panel relative w-full max-w-md overflow-hidden"
        style={{ padding: '28px 28px 24px' }}
      >
        {/* Bouton fermer */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 flex items-center justify-center rounded-md text-slate-500 hover:text-white transition-colors"
          style={{
            width: 28, height: 28,
            background: 'rgba(255,255,255,0.05)',
            border: '1px solid rgba(255,255,255,0.08)',
          }}
          aria-label="Fermer"
        >
          <X size={14} />
        </button>

        {/* Indicateur de progression */}
        <div className="mb-6">
          <StepDots total={STEPS.length} current={step} />
        </div>

        {/* Contenu animé */}
        <AnimatePresence mode="wait">
          {STEPS[step].render()}
        </AnimatePresence>

        {/* Navigation arrière */}
        {step > 0 && (
          <button
            onClick={() => setStep(s => s - 1)}
            className="mt-4 text-xs text-slate-600 hover:text-slate-400 transition-colors flex items-center gap-1 mx-auto"
          >
            ← Étape précédente
          </button>
        )}
      </motion.div>
    </motion.div>
  );
}
