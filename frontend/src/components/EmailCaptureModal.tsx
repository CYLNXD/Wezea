// ─── EmailCaptureModal — Lead capture + téléchargement PDF automatique ────────
//
// Flux UX (anonyme) :
//   1. L'utilisateur remplit son email
//   2. On appelle simultanément :
//      a. POST /report/request  → enregistrement CRM (lead)
//      b. POST /generate-pdf    → génération du PDF en mémoire
//   3. Dès que le PDF est prêt, le navigateur lance le téléchargement automatique
//   4. On affiche l'écran de succès avec confirmation
//
// Flux UX (connecté) :
//   → Pas de formulaire. Un bouton "Télécharger" suffit.
//     L'email de l'utilisateur est réutilisé automatiquement.
//
import { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  X, Mail, FileText,
  Loader2, CheckCircle2, Download, AlertCircle,
  FileDown, Shield, UserPlus, Lock,
} from 'lucide-react';
import { useLanguage } from '../i18n/LanguageContext';
import { generatePDF, downloadBlob, extractApiError } from '../lib/api';
import type { ScanResult } from '../types/scanner';

// ─────────────────────────────────────────────────────────────────────────────

interface Props {
  open:        boolean;
  onClose:     () => void;
  domain:      string;
  score:       number;
  scanResult:  ScanResult | null;   // ← données complètes pour le PDF
  userEmail?:  string;              // ← si connecté, on saute le formulaire
  onGoLogin?:  () => void;          // ← navigation vers inscription/connexion
}

type ModalState = 'idle' | 'loading' | 'generating_pdf' | 'success' | 'error';

// ─────────────────────────────────────────────────────────────────────────────

export function EmailCaptureModal({ open, onClose, domain, score, scanResult, userEmail, onGoLogin }: Props) {
  const { t, lang } = useLanguage();
  const [modalState, setModalState] = useState<ModalState>('idle');
  const [errorMsg,   setErrorMsg]   = useState('');
  const [pdfReady,   setPdfReady]   = useState(false);
  const [pdfBlob,    setPdfBlob]    = useState<Blob | null>(null);

  // Réinitialiser l'état à chaque fermeture du modal
  useEffect(() => {
    if (!open) {
      setModalState('idle');
      setErrorMsg('');
      setPdfReady(false);
      setPdfBlob(null);
    }
  }, [open]);

  const isCritical = score < 40;
  const isLoggedIn = !!userEmail;

  // ── Génération PDF (utilisée pour l'utilisateur connecté) ───────────────────
  // Note : on ne fait PAS appel à requestFullReport pour les utilisateurs
  // connectés — ils téléchargent directement, l'email serait redondant.
  const runGeneration = async (_email: string) => {
    setModalState('loading');
    setErrorMsg('');
    setPdfReady(false);
    setPdfBlob(null);

    try {
      let pdfPromise: Promise<Blob> | null = null;
      if (scanResult) {
        setModalState('generating_pdf');
        pdfPromise = generatePDF(scanResult, lang);
      }

      const [, blob] = await Promise.allSettled([
        Promise.resolve(null),          // pas d'email pour l'utilisateur connecté
        pdfPromise ?? Promise.resolve(null),
      ]).then(results => [
        results[0].status === 'fulfilled' ? results[0].value : null,
        results[1].status === 'fulfilled' ? results[1].value : null,
      ]);

      if (blob) {
        const filename = `cyberhealth-rapport-${domain}-${new Date().toISOString().slice(0, 10)}.pdf`;
        downloadBlob(blob as Blob, filename);
        setPdfBlob(blob as Blob);
        setPdfReady(true);
      }

      setModalState('success');
    } catch (err) {
      setErrorMsg(extractApiError(err));
      setModalState('error');
    }
  };

  // Bouton direct pour l'utilisateur connecté
  const handleDirectDownload = () => {
    if (userEmail) runGeneration(userEmail);
  };

  const handleRetryDownload = () => {
    if (pdfBlob) {
      const filename = `cyberhealth-rapport-${domain}.pdf`;
      downloadBlob(pdfBlob, filename);
    }
  };

  const reset = () => {
    setModalState('idle');
    setErrorMsg('');
    setPdfReady(false);
    onClose();
  };

  const isLoading = modalState === 'loading' || modalState === 'generating_pdf';

  // ── Texte du bouton selon l'état ───────────────────────────────────────────
  const buttonLabel = (() => {
    if (modalState === 'loading')        return t('modal_btn_loading');
    if (modalState === 'generating_pdf') return t('modal_btn_pdf');
    return scanResult ? t('modal_btn_download') : t('modal_btn_email');
  })();

  // ── Couleur accentuée selon score ──────────────────────────────────────────
  const accent = isCritical
    ? { from: 'from-red-700', to: 'to-orange-700', ring: 'ring-red-500/30', text: 'text-red-300', border: 'border-red-500/30' }
    : { from: 'from-cyan-600', to: 'to-blue-600',  ring: 'ring-cyan-500/30', text: 'text-cyan-300', border: 'border-cyan-500/30' };

  return createPortal(
    <AnimatePresence>
      {open && (
        <>
          {/* ── Overlay + centrage flex ────────────────────────────────── */}
          <motion.div
            key="overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={!isLoading ? reset : undefined}
            className="fixed inset-0 bg-black/75 backdrop-blur-sm z-40 flex items-center justify-center p-4"
          >
          {/* ── Modal — stoppons la propagation du click sur l'overlay ── */}
          <motion.div
            key="modal"
            initial={{ opacity: 0, scale: 0.93 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ type: 'spring', damping: 22, stiffness: 280 }}
            onClick={e => e.stopPropagation()}
            className="
              relative w-full max-w-[500px]
              bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl
              z-50 overflow-hidden max-h-[90vh] overflow-y-auto
            "
          >
            {/* ── Gradient header ──────────────────────────────────── */}
            <div className={`
              relative px-6 pt-6 pb-5 border-b border-slate-700
              bg-gradient-to-br from-slate-800 to-slate-900
            `}>
              {!isLoading && (
                <button
                  onClick={reset}
                  className="absolute top-4 right-4 text-slate-500 hover:text-slate-300 transition-colors"
                  aria-label="Fermer"
                >
                  <X size={18} />
                </button>
              )}

              {/* Icône + titre */}
              <div className="flex items-center gap-3 mb-3">
                <div className={`
                  p-2.5 rounded-xl border
                  ${isCritical
                    ? 'bg-red-500/10 border-red-500/30'
                    : 'bg-cyan-500/10 border-cyan-500/30'}
                `}>
                  <FileDown size={20} className={accent.text} />
                </div>
                <div>
                  <h2 className="text-white font-bold text-lg leading-tight">
                    {t('modal_title')}
                  </h2>
                  <p className="text-slate-400 text-xs mt-0.5">
                    {scanResult
                      ? t('modal_pdf_sub')
                      : t('modal_email_sub')}
                  </p>
                </div>
              </div>

              {/* Pitch contextuel selon score */}
              {isCritical ? (
                <div className="flex gap-2.5 bg-red-500/10 border border-red-500/25 rounded-xl p-3">
                  <AlertCircle size={15} className="text-red-400 mt-0.5 shrink-0" />
                  <p className="text-red-200 text-xs leading-relaxed">
                    {t('modal_critical_body', { score })}
                  </p>
                </div>
              ) : (
                <p className="text-slate-400 text-sm leading-relaxed">
                  {t('modal_normal_body_1')}{' '}
                  <strong className="text-slate-200">{t('modal_normal_body_pages')}</strong>{' '}
                  {t('modal_normal_body_2')}{' '}
                  <span className={`font-semibold ${accent.text}`}>{t('modal_consult')}</span>.
                </p>
              )}

              {/* Score pill */}
              <div className={`
                mt-3 inline-flex items-center gap-2
                bg-slate-950/60 px-3 py-1.5 rounded-lg border ${accent.border}
                text-xs font-mono
              `}>
                <Shield size={11} className={accent.text} />
                <span className="text-slate-500">{t('modal_score')}:</span>
                <span className={`font-bold ${
                  score < 40 ? 'text-red-400' : score < 70 ? 'text-orange-400' : 'text-green-400'
                }`}>{score}/100</span>
                <span className="text-slate-600">·</span>
                <span className="text-slate-400 font-mono">{domain}</span>
              </div>
            </div>

            {/* ── Corps du modal ───────────────────────────────────── */}
            <div className="px-6 py-5">
              <AnimatePresence mode="wait">

                {/* ── Vue connecté : pas de formulaire ────────────────── */}
                {modalState !== 'success' && isLoggedIn && (
                  <motion.div
                    key="logged-in"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0, y: -8 }}
                    className="flex flex-col gap-3"
                  >
                    {/* Email de l'utilisateur (affiché en lecture seule) */}
                    <div className="flex items-center gap-2.5 bg-slate-800/60 border border-slate-700 rounded-lg px-3 py-2.5 text-xs text-slate-400">
                      <Mail size={13} className="text-slate-500 shrink-0" />
                      <span className="flex-1 truncate">{userEmail}</span>
                      <span className="text-green-400 font-medium shrink-0">
                        {lang === 'fr' ? '✓ connecté' : '✓ signed in'}
                      </span>
                    </div>

                    {/* Message d'erreur */}
                    {modalState === 'error' && (
                      <motion.div
                        initial={{ opacity: 0, y: -4 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="flex gap-2 text-red-400 text-xs bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2.5"
                      >
                        <AlertCircle size={13} className="shrink-0 mt-0.5" />
                        <span>{errorMsg}</span>
                      </motion.div>
                    )}

                    {/* Progression PDF */}
                    {isLoading && (
                      <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        className="flex items-center gap-2.5 bg-slate-800/60 border border-slate-700 rounded-lg px-3 py-2.5 text-xs"
                      >
                        <Loader2 size={13} className={`animate-spin ${accent.text}`} />
                        <div className="flex-1">
                          <p className="text-slate-300 font-medium">
                            {modalState === 'generating_pdf' ? t('modal_gen_title') : t('modal_gen_sub')}
                          </p>
                          <p className="text-slate-500 mt-0.5">
                            {modalState === 'generating_pdf' ? t('modal_connect') : t('modal_legal')}
                          </p>
                        </div>
                      </motion.div>
                    )}

                    {/* Bouton télécharger direct */}
                    <button
                      type="button"
                      onClick={handleDirectDownload}
                      disabled={isLoading}
                      className={`
                        mt-1 flex items-center justify-center gap-2
                        w-full py-3 rounded-xl font-bold text-sm text-white
                        bg-gradient-to-r ${accent.from} ${accent.to}
                        hover:brightness-110
                        disabled:opacity-55 disabled:cursor-not-allowed
                        transition-all duration-200 shadow-lg ring-1 ${accent.ring}
                      `}
                    >
                      {isLoading ? (
                        <><Loader2 size={16} className="animate-spin" />{buttonLabel}</>
                      ) : (
                        <><Download size={16} />{lang === 'fr' ? 'Télécharger le rapport PDF' : 'Download PDF report'}</>
                      )}
                    </button>
                  </motion.div>
                )}

                {/* ── Vue anonyme : invitation à créer un compte ──────── */}
                {modalState !== 'success' && !isLoggedIn && (
                  <motion.div
                    key="signup-required"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0, y: -8 }}
                    className="flex flex-col gap-4"
                  >
                    {/* Explication */}
                    <div className="flex gap-3 bg-slate-800/60 border border-slate-700 rounded-xl p-4">
                      <div className="p-2 rounded-lg bg-cyan-500/10 border border-cyan-500/20 shrink-0 self-start">
                        <Lock size={14} className="text-cyan-400" />
                      </div>
                      <p className="text-slate-400 text-sm leading-relaxed">
                        {lang === 'fr'
                          ? 'Le rapport PDF complet est réservé aux membres. Créez un compte gratuit en moins de 30 secondes pour y accéder.'
                          : 'The full PDF report is reserved for members. Create a free account in under 30 seconds to access it.'}
                      </p>
                    </div>

                    {/* Avantages compte gratuit */}
                    <div className="bg-slate-800/40 border border-slate-700/60 rounded-xl p-4">
                      <p className="text-slate-300 text-xs font-semibold mb-3 flex items-center gap-1.5">
                        <Shield size={12} className="text-cyan-400" />
                        {lang === 'fr' ? 'Compte gratuit — inclus' : 'Free account — included'}
                      </p>
                      <ul className="space-y-2">
                        {(lang === 'fr' ? [
                          'Rapport PDF complet téléchargeable',
                          '5 scans par semaine',
                          'Historique de vos analyses',
                          'Aucune carte bancaire requise',
                        ] : [
                          'Full PDF report download',
                          '5 scans per week',
                          'Scan history',
                          'No credit card required',
                        ]).map((item, i) => (
                          <li key={i} className="flex items-center gap-2 text-xs text-slate-400">
                            <CheckCircle2 size={12} className="text-green-400 shrink-0" />
                            {item}
                          </li>
                        ))}
                      </ul>
                    </div>

                    {/* CTA inscription */}
                    <button
                      type="button"
                      onClick={() => { onClose(); onGoLogin?.(); }}
                      className="flex items-center justify-center gap-2 w-full py-3 rounded-xl font-bold text-sm text-white bg-gradient-to-r from-cyan-600 to-blue-600 hover:brightness-110 transition-all shadow-lg ring-1 ring-cyan-500/30"
                    >
                      <UserPlus size={16} />
                      {lang === 'fr' ? 'Créer mon compte gratuit' : 'Create my free account'}
                    </button>

                    {/* Lien connexion */}
                    <p className="text-center text-xs text-slate-500">
                      {lang === 'fr' ? 'Déjà un compte ?' : 'Already have an account?'}{' '}
                      <button
                        type="button"
                        onClick={() => { onClose(); onGoLogin?.(); }}
                        className="text-cyan-400 hover:text-cyan-300 transition-colors font-medium"
                      >
                        {lang === 'fr' ? 'Se connecter →' : 'Sign in →'}
                      </button>
                    </p>
                  </motion.div>
                )}

                {/* ── Succès + téléchargement ──────────────────────── */}
                {modalState === 'success' && (
                  <motion.div
                    key="success"
                    initial={{ opacity: 0, scale: 0.94 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ duration: 0.3 }}
                    className="flex flex-col items-center gap-4 py-4 text-center"
                  >
                    {/* Icône animée */}
                    <motion.div
                      initial={{ scale: 0 }}
                      animate={{ scale: 1 }}
                      transition={{ type: 'spring', damping: 12, stiffness: 200 }}
                      className="p-4 rounded-full bg-green-500/10 border border-green-500/30"
                    >
                      <CheckCircle2 size={38} className="text-green-400" />
                    </motion.div>

                    <div>
                      <h3 className="text-white font-bold text-xl mb-1">
                        {pdfReady ? t('modal_success_pdf') : t('modal_success_req')}
                      </h3>
                      <p className="text-slate-400 text-sm leading-relaxed max-w-xs">
                        {pdfReady
                          ? t('modal_success_pdf_body')
                          : t('modal_success_email_body', { email: userEmail ?? '' })}
                      </p>
                    </div>

                    {/* Actions post-succès */}
                    <div className="flex flex-col gap-2 w-full">
                      {/* Re-télécharger si PDF disponible */}
                      {pdfBlob && (
                        <button
                          onClick={handleRetryDownload}
                          className={`
                            flex items-center justify-center gap-2 w-full py-2.5 rounded-xl
                            bg-gradient-to-r ${accent.from} ${accent.to}
                            text-white font-semibold text-sm
                            hover:brightness-110 transition-all
                          `}
                        >
                          <FileText size={15} />
                          {t('modal_redownload')}
                        </button>
                      )}

                      {/* Prochaines étapes */}
                      <div className="bg-slate-800/60 border border-slate-700 rounded-xl p-4 text-left w-full">
                        <p className="text-slate-300 text-xs font-semibold mb-2 flex items-center gap-1.5">
                          <Shield size={12} className="text-cyan-400" />
                          {t('modal_next_steps')}
                        </p>
                        <ul className="text-slate-500 text-xs space-y-1.5">
                          <li className="flex gap-2">
                            <span className="text-cyan-400 shrink-0">→</span>
                            {t('modal_step1')}
                          </li>
                          <li className="flex gap-2">
                            <span className="text-cyan-400 shrink-0">→</span>
                            {t('modal_step2')}
                          </li>
                          <li className="flex gap-2">
                            <span className="text-cyan-400 shrink-0">→</span>
                            {t('modal_step3')}
                          </li>
                        </ul>
                      </div>

                      <button
                        onClick={reset}
                        className="py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 text-sm font-medium transition-colors"
                      >
                        {t('btn_close')}
                      </button>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </motion.div>
          </motion.div>
        </>
      )}
    </AnimatePresence>,
    document.body
  );
}

