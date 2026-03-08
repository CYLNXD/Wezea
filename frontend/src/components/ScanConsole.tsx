// ─── ScanConsole — Terminal animé simulant les étapes du scan ─────────────────
import { useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Terminal, Loader2 } from 'lucide-react';
import { useLanguage } from '../i18n/LanguageContext';
import type { ConsoleLog } from '../types/scanner';

interface Props {
  logs:     ConsoleLog[];
  progress: number;       // 0–100
  domain:   string;
}

// Couleurs par type de log
const LOG_COLORS: Record<ConsoleLog['type'], string> = {
  system:  'text-cyan-400 font-bold',
  info:    'text-slate-300',
  success: 'text-green-400',
  warning: 'text-amber-400',
  error:   'text-red-400',
};

const LOG_PREFIXES: Record<ConsoleLog['type'], string> = {
  system:  '[SYS] ',
  info:    '[INF] ',
  success: '[OK]  ',
  warning: '[WRN] ',
  error:   '[ERR] ',
};

export function ScanConsole({ logs, progress, domain }: Props) {
  const { t, lang } = useLanguage();
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll vers le bas à chaque nouveau log
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -16 }}
      transition={{ duration: 0.4, ease: 'easeOut' }}
      className="w-full max-w-3xl mx-auto"
    >
      {/* Fenêtre terminal */}
      <div className="rounded-xl overflow-hidden" style={{ background: '#080e17', border: '1px solid rgba(255,255,255,0.07)', boxShadow: '0 8px 32px rgba(0,0,0,0.7), 0 1px 0 rgba(255,255,255,0.05) inset' }}>

        {/* Barre de titre façon terminal macOS */}
        <div className="flex items-center gap-2 px-4 py-3" style={{ background: 'linear-gradient(180deg,#141c26,#0f161f)', borderBottom: '1px solid rgba(255,255,255,0.06)', boxShadow: '0 1px 0 rgba(0,0,0,0.4)' }}>
          {/* Dots avec effet 3D */}
          <span className="w-3 h-3 rounded-full" style={{ background: 'radial-gradient(circle at 35% 35%, #ff6b6b, #e03535)', boxShadow: '0 1px 2px rgba(0,0,0,0.5)' }} />
          <span className="w-3 h-3 rounded-full" style={{ background: 'radial-gradient(circle at 35% 35%, #ffd93d, #d4a017)', boxShadow: '0 1px 2px rgba(0,0,0,0.5)' }} />
          <span className="w-3 h-3 rounded-full" style={{ background: 'radial-gradient(circle at 35% 35%, #6bcb77, #28a745)', boxShadow: '0 1px 2px rgba(0,0,0,0.5)' }} />
          <div className="flex items-center gap-2 ml-4 text-slate-400 text-xs font-mono">
            <Terminal size={13} />
            <span>{t('console_title', { domain })}</span>
          </div>
          {/* Spinner actif */}
          <Loader2
            size={13}
            className="ml-auto text-cyan-400 animate-spin"
          />
        </div>

        {/* Corps du terminal */}
        <div className="h-52 sm:h-72 overflow-y-auto overflow-x-hidden p-3 sm:p-4 font-mono text-xs leading-relaxed">
          <AnimatePresence initial={false}>
            {logs.map((log) => (
              <motion.div
                key={log.id}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.18 }}
                className="flex gap-2 mb-1"
              >
                <span className="text-slate-600 select-none shrink-0">
                  {log.timestamp}
                </span>
                <span className={`${LOG_COLORS[log.type]} break-words min-w-0`}>
                  <span className="text-slate-500">{LOG_PREFIXES[log.type]}</span>
                  {log.message}
                </span>
              </motion.div>
            ))}
          </AnimatePresence>

          {/* Curseur clignotant */}
          <div className="flex items-center gap-1 mt-1">
            <span className="text-slate-600 text-xs">
              {new Date().toLocaleTimeString(lang === 'en' ? 'en-GB' : 'fr-FR', { hour12: false })}
            </span>
            <span className="text-slate-500 text-xs ml-2">[INF] </span>
            <motion.span
              animate={{ opacity: [1, 0, 1] }}
              transition={{ duration: 1, repeat: Infinity }}
              className="inline-block w-2 h-3 bg-cyan-400 rounded-sm"
            />
          </div>
          <div ref={bottomRef} />
        </div>

        {/* Barre de progression */}
        <div className="px-4 py-3" style={{ background: 'linear-gradient(180deg,#0d1420,#0a1018)', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
          <div className="flex items-center justify-between mb-2 text-xs font-mono">
            <span className="text-slate-500">{t('console_scanning')}</span>
            <span className="font-semibold" style={{ color: 'var(--color-accent)' }}>{progress}%</span>
          </div>
          <div className="sku-progress-track h-1.5">
            <motion.div
              className="sku-progress-fill rounded-full"
              initial={{ width: '0%' }}
              animate={{ width: `${progress}%` }}
              transition={{ duration: 0.3, ease: 'easeOut' }}
            />
          </div>
        </div>
      </div>

      {/* Texte statut en dessous */}
      <motion.p
        animate={{ opacity: [0.5, 1, 0.5] }}
        transition={{ duration: 2, repeat: Infinity }}
        className="text-center text-slate-500 text-sm font-mono mt-4"
      >
        {t('console_passive')}
      </motion.p>
    </motion.div>
  );
}
