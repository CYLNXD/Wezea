// ─── CTABanner — Bandeau fixe en bas si score < 60 ───────────────────────────
import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { AlertTriangle, X, MessageSquare } from 'lucide-react';
import { useLanguage } from '../i18n/LanguageContext';

interface Props {
  score:        number;
  domain:       string;
  onGoContact?: () => void;
}

export function CTABanner({ score, domain, onGoContact }: Props) {
  const [dismissed, setDismissed] = useState(false);
  const { t, lang } = useLanguage();

  // Apparaît uniquement si score < 60
  const show = score < 60 && !dismissed;

  // Texte adapté selon criticité
  const isCritical = score < 40;
  const urgencyLabel = isCritical
    ? t('cta_title_critical')
    : t('cta_title_high');
  const urgencyDesc = isCritical
    ? t('cta_body_critical', { score, domain })
    : t('cta_body_high', { score });

  return (
    <AnimatePresence>
      {show && (
        <motion.div
          key="cta-banner"
          initial={{ y: 100, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 100, opacity: 0 }}
          transition={{ type: 'spring', damping: 24, stiffness: 200, delay: 1.2 }}
          className="fixed bottom-0 left-0 right-0 z-30"
        >
          {/* Fond dégradé + blur */}
          <div className={`
            relative border-t
            ${isCritical
              ? 'bg-red-950/95 border-red-500/40'
              : 'bg-orange-950/95 border-orange-500/35'}
            backdrop-blur-md
          `}>
            {/* Ligne lumineuse en haut */}
            <div className={`
              absolute top-0 left-0 right-0 h-px
              ${isCritical
                ? 'bg-gradient-to-r from-transparent via-red-500 to-transparent'
                : 'bg-gradient-to-r from-transparent via-orange-500 to-transparent'}
            `} />

            <div className="max-w-6xl mx-auto px-4 py-4 md:py-3">
              <div className="flex flex-col md:flex-row items-start md:items-center gap-4">

                {/* Icône + texte */}
                <div className="flex items-start gap-3 flex-1">
                  <div className={`
                    p-2 rounded-lg shrink-0 mt-0.5
                    ${isCritical ? 'bg-red-500/20' : 'bg-orange-500/20'}
                  `}>
                    <AlertTriangle
                      size={18}
                      className={isCritical ? 'text-red-400' : 'text-orange-400'}
                    />
                  </div>
                  <div>
                    <p className={`font-bold text-sm ${isCritical ? 'text-red-300' : 'text-orange-300'}`}>
                      {urgencyLabel}
                    </p>
                    <p className="text-slate-300 text-xs mt-0.5 leading-relaxed">
                      {urgencyDesc}
                    </p>
                  </div>
                </div>

                {/* CTAs */}
                <div className="flex items-center gap-2 w-full md:w-auto shrink-0">
                  <button
                    onClick={onGoContact}
                    className={`
                      flex items-center gap-2 px-4 py-2.5 rounded-xl
                      font-bold text-sm text-white flex-1 md:flex-none
                      transition-all duration-200 shadow-lg
                      ${isCritical
                        ? 'bg-red-600 hover:bg-red-500 shadow-red-900/50'
                        : 'bg-orange-600 hover:bg-orange-500 shadow-orange-900/50'}
                    `}
                  >
                    <MessageSquare size={15} />
                    {lang === 'fr' ? 'Contactez-nous' : 'Contact us'}
                  </button>
                </div>

                {/* Bouton fermer */}
                <button
                  onClick={() => setDismissed(true)}
                  className="absolute top-3 right-3 text-slate-600 hover:text-slate-400 transition-colors"
                  aria-label="Fermer"
                >
                  <X size={16} />
                </button>
              </div>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
