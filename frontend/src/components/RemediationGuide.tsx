// ─── RemediationGuide — Guide de remédiation pas-à-pas ──────────────────────
import { useState, useEffect, type ReactNode } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Wrench, ChevronDown, ChevronUp, Clock, Lock,
  MapPin, CheckSquare, Zap,
} from 'lucide-react';
import { apiClient } from '../lib/api';
import { useLanguage } from '../i18n/LanguageContext';

function SkuIcon({ children, color, size = 32 }: { children: ReactNode; color: string; size?: number }) {
  const r = Math.round(size * 0.28);
  return (
    <div className="shrink-0 flex items-center justify-center relative overflow-hidden"
      style={{
        width: size, height: size, borderRadius: r,
        background: `linear-gradient(150deg, ${color}30 0%, ${color}0d 100%)`,
        border: `1px solid ${color}40`,
        boxShadow: `0 4px 16px ${color}22, 0 1px 3px rgba(0,0,0,0.4), inset 0 1px 0 ${color}30, inset 0 -1px 0 rgba(0,0,0,0.3)`,
      }}
    >
      <div className="absolute inset-0 pointer-events-none"
        style={{ borderRadius: r, background: 'linear-gradient(180deg,rgba(255,255,255,0.07) 0%,transparent 50%)' }} />
      {children}
    </div>
  );
}

interface RemediationStep {
  order:  number;
  action: string;
  where:  string;
  verify: string;
}

interface GuideData {
  key:                string;
  title:              string;
  difficulty:         string;
  estimated_time_min: number;
  step_count:         number;
  is_premium:         boolean;
  locked:             boolean;
  steps:              RemediationStep[];
}

const DIFFICULTY_CONFIG: Record<string, { label_fr: string; label_en: string; color: string }> = {
  easy:     { label_fr: 'Facile',   label_en: 'Easy',     color: '#4ade80' },
  medium:   { label_fr: 'Moyen',    label_en: 'Medium',   color: '#fbbf24' },
  advanced: { label_fr: 'Avancé',   label_en: 'Advanced', color: '#f87171' },
};

interface Props {
  findingTitle: string;
  onUpgrade?: () => void;
}

export default function RemediationGuide({ findingTitle, onUpgrade }: Props) {
  const { lang } = useLanguage();
  const [guide, setGuide] = useState<GuideData | null>(null);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (!open || guide || notFound) return;
    setLoading(true);
    apiClient
      .get('/remediation/guide', { params: { title: findingTitle, lang } })
      .then(r => setGuide(r.data))
      .catch(err => {
        if (err?.response?.status === 404) setNotFound(true);
      })
      .finally(() => setLoading(false));
  }, [open, findingTitle, lang, guide, notFound]);

  if (notFound) return null;

  const diffCfg = guide ? DIFFICULTY_CONFIG[guide.difficulty] : null;

  return (
    <div className="mt-3">
      {/* Toggle button */}
      <button
        onClick={() => setOpen(v => !v)}
        className="flex items-center gap-2 text-xs font-medium transition-colors"
        style={{ color: '#a78bfa' }}
      >
        <Wrench size={13} />
        <span>{lang === 'fr' ? 'Guide pas-à-pas' : 'Step-by-step guide'}</span>
        {open ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="overflow-hidden"
          >
            <div
              className="mt-3 rounded-xl p-4"
              style={{
                background: 'rgba(0,0,0,0.3)',
                border: '1px solid rgba(167, 139, 250, 0.15)',
              }}
            >
              {loading && (
                <div className="flex items-center gap-2 text-xs text-slate-500">
                  <div className="w-4 h-4 border-2 border-violet-400 border-t-transparent rounded-full animate-spin" />
                  {lang === 'fr' ? 'Chargement…' : 'Loading…'}
                </div>
              )}

              {guide && !guide.locked && (
                <>
                  {/* Header */}
                  <div className="flex items-start gap-3 mb-4">
                    <SkuIcon color="#a78bfa" size={32}>
                      <Wrench size={16} className="text-violet-300" />
                    </SkuIcon>
                    <div className="flex-1 min-w-0">
                      <h4 className="text-sm font-semibold text-slate-200">{guide.title}</h4>
                      <div className="flex flex-wrap items-center gap-3 mt-1.5">
                        {diffCfg && (
                          <span
                            className="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full"
                            style={{ color: diffCfg.color, background: `${diffCfg.color}18`, border: `1px solid ${diffCfg.color}30` }}
                          >
                            {lang === 'fr' ? diffCfg.label_fr : diffCfg.label_en}
                          </span>
                        )}
                        <span className="flex items-center gap-1 text-[10px] text-slate-500">
                          <Clock size={11} />
                          ~{guide.estimated_time_min} min
                        </span>
                        <span className="text-[10px] text-slate-500">
                          {guide.step_count} {lang === 'fr' ? 'étapes' : 'steps'}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Steps */}
                  <div className="flex flex-col gap-3">
                    {guide.steps.map((step) => (
                      <div key={step.order} className="flex gap-3">
                        {/* Step number */}
                        <div
                          className="shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold"
                          style={{
                            background: 'rgba(167, 139, 250, 0.15)',
                            border: '1px solid rgba(167, 139, 250, 0.3)',
                            color: '#c4b5fd',
                          }}
                        >
                          {step.order}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-xs text-slate-200 leading-relaxed">{step.action}</p>
                          {step.where && (
                            <div className="flex items-start gap-1.5 mt-1.5">
                              <MapPin size={11} className="text-slate-500 mt-0.5 shrink-0" />
                              <p className="text-[11px] text-slate-500 leading-snug">{step.where}</p>
                            </div>
                          )}
                          {step.verify && (
                            <div className="flex items-start gap-1.5 mt-1.5">
                              <CheckSquare size={11} className="text-green-500 mt-0.5 shrink-0" />
                              <p className="text-[11px] text-green-400/70 font-mono leading-snug">{step.verify}</p>
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              )}

              {guide && guide.locked && (
                <div className="text-center py-4">
                  <div className="flex justify-center mb-3">
                    <SkuIcon color="#a78bfa" size={44}>
                      <Lock size={20} className="text-violet-300" />
                    </SkuIcon>
                  </div>
                  <h4 className="text-sm font-semibold text-slate-200 mb-1">{guide.title}</h4>
                  <div className="flex justify-center items-center gap-3 mb-3">
                    {diffCfg && (
                      <span
                        className="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full"
                        style={{ color: diffCfg.color, background: `${diffCfg.color}18`, border: `1px solid ${diffCfg.color}30` }}
                      >
                        {lang === 'fr' ? diffCfg.label_fr : diffCfg.label_en}
                      </span>
                    )}
                    <span className="flex items-center gap-1 text-[10px] text-slate-500">
                      <Clock size={11} />
                      ~{guide.estimated_time_min} min
                    </span>
                    <span className="text-[10px] text-slate-500">
                      {guide.step_count} {lang === 'fr' ? 'étapes' : 'steps'}
                    </span>
                  </div>
                  <p className="text-xs text-slate-500 mb-3">
                    {lang === 'fr'
                      ? 'Ce guide détaillé est disponible avec un abonnement Starter ou supérieur.'
                      : 'This detailed guide is available with a Starter plan or above.'}
                  </p>
                  {onUpgrade && (
                    <button onClick={onUpgrade} className="sku-btn-primary text-xs px-4 py-2 rounded-lg flex items-center gap-2 mx-auto">
                      <Zap size={13} />
                      {lang === 'fr' ? 'Voir les plans' : 'View plans'}
                    </button>
                  )}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
