// ─── FindingCard — Carte de vulnérabilité avec explication vulgarisée ─────────
import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  AlertTriangle, ChevronDown, ChevronUp,
  ShieldX, Info, CheckCircle,
  Lightbulb, Code2,
} from 'lucide-react';
import { useLanguage } from '../i18n/LanguageContext';
import { SEVERITY_CONFIG } from '../types/scanner';
import type { Finding, Severity } from '../types/scanner';

interface Props {
  finding: Finding;
  index:   number;
}

const SEVERITY_ICONS: Record<Severity, React.ReactNode> = {
  CRITICAL: <ShieldX   size={18} />,
  HIGH:     <AlertTriangle size={17} />,
  MEDIUM:   <AlertTriangle size={17} />,
  LOW:      <CheckCircle size={17} />,
  INFO:     <Info       size={17} />,
};

const SEVERITY_KEYS: Record<Severity, string> = {
  CRITICAL: 'sev_critical',
  HIGH:     'sev_high',
  MEDIUM:   'sev_medium',
  LOW:      'sev_low',
  INFO:     'sev_info',
};

const CATEGORY_KEYS: Record<string, string> = {
  'DNS & Mail':                    'cat_dns',
  'SSL / HTTPS':                   'cat_ssl',
  'Exposition des Ports':          'cat_ports',
  'En-têtes HTTP':                 'cat_headers',
  'Sécurité Email':                'cat_email_sec',
  'Exposition Technologique':      'cat_tech',
  'Réputation du Domaine':         'cat_reputation',
  'Versions Vulnérables':          'cat_vuln_versions',
  'Sous-domaines & Certificats':   'cat_subdomains',
};

export function FindingCard({ finding, index }: Props) {
  const { t } = useLanguage();
  const [expanded, setExpanded] = useState(
    finding.severity === 'CRITICAL' || finding.severity === 'HIGH'
  );

  const cfg = SEVERITY_CONFIG[finding.severity];

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: index * 0.06, ease: 'easeOut' }}
      className={`
        rounded-xl border relative overflow-hidden transition-all duration-200
        finding-${finding.severity.toLowerCase()}
      `}
    >
      {/* ── Header de la carte ─────────────────────────────────────────── */}
      <button
        onClick={() => setExpanded(v => !v)}
        className="w-full flex items-start gap-3 p-5 text-left group"
        aria-expanded={expanded}
      >
        {/* Icône sévérité */}
        <span className={`mt-0.5 shrink-0 ${cfg.icon}`}>
          {SEVERITY_ICONS[finding.severity]}
        </span>

        {/* Contenu principal */}
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-2">
            {/* Badge sévérité */}
            <span className={`sku-badge text-[10px] ${cfg.badge}`}>
              {t(SEVERITY_KEYS[finding.severity] as any)}
            </span>
            {/* Badge catégorie */}
            <span className="text-xs text-slate-500 font-mono">
              {t((CATEGORY_KEYS[finding.category] ?? 'cat_reputation') as any)}
            </span>
            {/* Pénalité */}
            {(finding.penalty ?? 0) > 0 && (
              <span className="ml-auto text-xs font-mono text-slate-500 shrink-0">
                −{finding.penalty} pts
              </span>
            )}
          </div>
          <p className={`font-semibold text-xs leading-snug ${cfg.text}`}>
            {finding.title ?? finding.message}
          </p>
        </div>

        {/* Chevron */}
        <span className="text-slate-600 group-hover:text-slate-400 transition-colors shrink-0 mt-1">
          {expanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
        </span>
      </button>

      {/* ── Corps expansible ───────────────────────────────────────────── */}
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            key="content"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: 'easeInOut' }}
            className="overflow-hidden"
          >
            <div className="px-5 pb-5 pt-0 flex flex-col gap-4">

              {/* Séparateur */}
              <div className="h-px" style={{ background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.07), transparent)' }} />

              {/* Explication vulgarisée — uniquement si disponible */}
              {finding.plain_explanation && (
                <div className="flex gap-3">
                  <span className="text-amber-400 mt-0.5 shrink-0">
                    <Lightbulb size={16} />
                  </span>
                  <div>
                    <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-1.5">
                      {t('finding_meaning')}
                    </p>
                    <p className="text-slate-200 text-xs leading-relaxed">
                      {finding.plain_explanation}
                    </p>
                  </div>
                </div>
              )}

              {/* Détail technique — uniquement si disponible */}
              {finding.technical_detail && (
                <div className="flex gap-3">
                  <span className="text-slate-500 mt-0.5 shrink-0">
                    <Code2 size={16} />
                  </span>
                  <div>
                    <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-1.5">
                      {t('finding_technical')}
                    </p>
                    <p className="sku-code-box text-slate-400 text-xs font-mono leading-relaxed px-3 py-2">
                      {finding.technical_detail}
                    </p>
                  </div>
                </div>
              )}

              {/* Recommandation */}
              <div className="flex gap-3 rounded-lg p-4" style={{ background: 'rgba(0,0,0,0.25)', border: '1px solid rgba(255,255,255,0.05)', boxShadow: '0 1px 4px rgba(0,0,0,0.4) inset' }}>
                <span className="text-cyan-400 mt-0.5 shrink-0">
                  <CheckCircle size={16} />
                </span>
                <div>
                  <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-1.5">
                    {t('finding_reco')}
                  </p>
                  <p className="text-cyan-200 text-xs leading-relaxed">
                    {finding.recommendation}
                  </p>
                </div>
              </div>

            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

// ── Groupe de cartes par catégorie ────────────────────────────────────────────

interface GroupProps {
  title:    string;
  findings: Finding[];
  startIdx: number;
}

export function FindingGroup({ title, findings, startIdx }: GroupProps) {
  if (findings.length === 0) return null;

  const hasCritical = findings.some(f => f.severity === 'CRITICAL');
  const hasHigh     = findings.some(f => f.severity === 'HIGH');
  const headerClass = hasCritical
    ? 'text-red-400'
    : hasHigh
    ? 'text-orange-400'
    : 'text-slate-400';

  return (
    <div className="flex flex-col gap-4">
      <h3 className={`text-[10px] font-mono uppercase tracking-widest ${headerClass} flex items-center gap-2`}
        style={{ letterSpacing: '0.1em' }}
      >
        <span className="flex-1 h-px bg-current opacity-15" />
        {title}
        <span className="flex-1 h-px bg-current opacity-15" />
      </h3>
      {findings.map((f, i) => (
        <FindingCard key={(f.title ?? f.message ?? '') + i} finding={f} index={startIdx + i} />
      ))}
    </div>
  );
}
