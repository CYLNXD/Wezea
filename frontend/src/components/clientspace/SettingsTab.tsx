// ─── SettingsTab — Profile, Billing, White-label, Danger zone ──────────────────
import React from 'react';
import {
  Key, Shield, Mail, CreditCard, AlertTriangle,
  Check, RefreshCw, Trash2, X,
} from 'lucide-react';
import SkuIcon from '../SkuIcon';
import { getWhiteLabel, updateWhiteLabel, uploadWhiteLabelLogo, deleteWhiteLabelLogo } from '../../lib/api';
import type { WhiteLabelSettings } from '../../lib/api';

// ─── Props ──────────────────────────────────────────────────────────────────────

export interface SettingsTabProps {
  user: any;
  settingsSection: 'profile' | 'billing' | 'whitelabel' | 'danger';
  setSettingsSection: (v: 'profile' | 'billing' | 'whitelabel' | 'danger') => void;
  isPremium: boolean;
  lang: 'fr' | 'en';

  // Email change
  newEmail: string;
  setNewEmail: (v: string) => void;
  emailPassword: string;
  setEmailPassword: (v: string) => void;
  emailLoading: boolean;
  emailMsg: { type: 'ok' | 'err'; text: string } | null;
  handleChangeEmail: () => void;

  // Password change
  currentPwd: string;
  setCurrentPwd: (v: string) => void;
  newPwd: string;
  setNewPwd: (v: string) => void;
  confirmPwd: string;
  setConfirmPwd: (v: string) => void;
  pwdLoading: boolean;
  pwdMsg: { type: 'ok' | 'err'; text: string } | null;
  handleChangePassword: () => void;

  // 2FA
  mfaStep: null | 'setup' | 'disabling';
  setMfaStep: (v: null | 'setup' | 'disabling') => void;
  mfaQrCode: string;
  mfaSecret: string;
  mfaCode: string;
  setMfaCode: (v: string) => void;
  mfaDisablePwd: string;
  setMfaDisablePwd: (v: string) => void;
  mfaLoading: boolean;
  mfaMsg: { type: 'ok' | 'err'; text: string } | null;
  setMfaMsg: (v: { type: 'ok' | 'err'; text: string } | null) => void;
  handleMfaSetup: () => void;
  handleMfaVerify: () => void;
  handleMfaDisable: () => void;

  // Billing
  portalLoading: boolean;
  handlePortal: () => void;

  // White-label
  wb: WhiteLabelSettings | null;
  setWb: React.Dispatch<React.SetStateAction<WhiteLabelSettings | null>>;
  wbLoading: boolean;
  wbSaving: boolean;
  setWbSaving: (v: boolean) => void;
  wbMsg: { type: 'ok' | 'err'; text: string } | null;
  setWbMsg: (v: { type: 'ok' | 'err'; text: string } | null) => void;
  wbName: string;
  setWbName: (v: string) => void;
  wbColor: string;
  setWbColor: (v: string) => void;
  wbEnabled: boolean;
  setWbEnabled: React.Dispatch<React.SetStateAction<boolean>>;
  wbLogoUploading: boolean;
  setWbLogoUploading: (v: boolean) => void;

  // Danger zone
  setShowDeleteModal: (v: boolean) => void;
}

// ─── Component ──────────────────────────────────────────────────────────────────

export default function SettingsTab({
  user,
  settingsSection, setSettingsSection,
  isPremium,
  lang,
  // Email
  newEmail, setNewEmail,
  emailPassword, setEmailPassword,
  emailLoading, emailMsg,
  handleChangeEmail,
  // Password
  currentPwd, setCurrentPwd,
  newPwd, setNewPwd,
  confirmPwd, setConfirmPwd,
  pwdLoading, pwdMsg,
  handleChangePassword,
  // 2FA
  mfaStep, setMfaStep,
  mfaQrCode, mfaSecret,
  mfaCode, setMfaCode,
  mfaDisablePwd, setMfaDisablePwd,
  mfaLoading, mfaMsg, setMfaMsg,
  handleMfaSetup, handleMfaVerify, handleMfaDisable,
  // Billing
  portalLoading, handlePortal,
  // White-label
  wb, setWb,
  wbLoading, wbSaving, setWbSaving,
  wbMsg, setWbMsg,
  wbName, setWbName,
  wbColor, setWbColor,
  wbEnabled, setWbEnabled,
  wbLogoUploading, setWbLogoUploading,
  // Danger
  setShowDeleteModal,
}: SettingsTabProps) {
  return (
    <div className="flex flex-col gap-5">

      {/* Sub-nav */}
      <div className="flex gap-2 flex-wrap">
        {([
          { id: 'profile'     as const, label: lang === 'fr' ? 'Profil & Sécurité' : 'Profile & Security', icon: <Key size={13} /> },
          { id: 'billing'     as const, label: lang === 'fr' ? 'Facturation' : 'Billing',                  icon: <CreditCard size={13} /> },
          ...(user?.plan && (user.plan === 'pro' || user.plan === 'dev') ? [{
            id: 'whitelabel' as const,
            label: lang === 'fr' ? 'Marque blanche' : 'White-label',
            icon: <Shield size={13} />,
          }] : []),
          { id: 'danger'      as const, label: lang === 'fr' ? 'Zone dangereuse' : 'Danger zone',          icon: <AlertTriangle size={13} /> },
        ]).map(s => (
          <button
            key={s.id}
            onClick={() => setSettingsSection(s.id)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition border ${
              settingsSection === s.id
                ? s.id === 'danger'
                  ? 'bg-red-500/20 text-red-400 border-red-500/30'
                  : 'bg-cyan-500/15 text-cyan-400 border-cyan-500/30'
                : 'text-slate-500 border-slate-800 hover:border-slate-700 hover:text-slate-300'
            }`}
          >
            {s.icon}{s.label}
          </button>
        ))}
      </div>

      {/* ── PROFILE & SECURITY ── */}
      {settingsSection === 'profile' && (
        <div className="flex flex-col gap-4">

          {/* Change email */}
          <div className="sku-card rounded-xl p-5">
            <div className="flex items-center gap-3 mb-4">
              <SkuIcon color="#22d3ee" size={32}><Mail size={13} className="text-cyan-300" /></SkuIcon>
              <h3 className="text-white font-semibold text-sm">{lang === 'fr' ? 'Adresse email' : 'Email address'}</h3>
            </div>
            {user?.google_id ? (
              <p className="text-slate-400 text-xs">
                {lang === 'fr' ? 'Votre compte est lié à Google. L\'email est géré par Google.' : 'Your account is linked to Google. Email is managed by Google.'}
              </p>
            ) : (
              <>
                <p className="text-slate-500 text-xs mb-4">
                  {lang === 'fr' ? 'Email actuel :' : 'Current email:'}{' '}
                  <span className="text-slate-300 font-mono">{user?.email}</span>
                </p>
                {emailMsg && (
                  <div className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs mb-3 ${emailMsg.type === 'ok' ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>
                    {emailMsg.type === 'ok' ? <Check size={12} /> : <AlertTriangle size={12} />}
                    {emailMsg.text}
                  </div>
                )}
                <div className="flex flex-col gap-3">
                  <input
                    type="email"
                    placeholder={lang === 'fr' ? 'Nouvel email' : 'New email'}
                    value={newEmail}
                    onChange={e => setNewEmail(e.target.value)}
                    className="w-full bg-slate-800/60 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 outline-none focus:border-cyan-500/50 placeholder-slate-600"
                  />
                  <input
                    type="password"
                    placeholder={lang === 'fr' ? 'Mot de passe actuel (confirmation)' : 'Current password (confirmation)'}
                    value={emailPassword}
                    onChange={e => setEmailPassword(e.target.value)}
                    className="w-full bg-slate-800/60 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 outline-none focus:border-cyan-500/50 placeholder-slate-600"
                  />
                  <button
                    onClick={handleChangeEmail}
                    disabled={emailLoading || !newEmail || !emailPassword}
                    className="self-start flex items-center gap-2 bg-cyan-500/15 hover:bg-cyan-500/25 border border-cyan-500/30 text-cyan-400 px-4 py-2 rounded-lg text-xs font-semibold transition disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {emailLoading ? <RefreshCw size={12} className="animate-spin" /> : <Check size={12} />}
                    {lang === 'fr' ? 'Mettre à jour l\'email' : 'Update email'}
                  </button>
                </div>
              </>
            )}
          </div>

          {/* Change password */}
          <div className="sku-card rounded-xl p-5">
            <div className="flex items-center gap-3 mb-4">
              <SkuIcon color="#818cf8" size={32}><Key size={13} className="text-indigo-300" /></SkuIcon>
              <h3 className="text-white font-semibold text-sm">{lang === 'fr' ? 'Mot de passe' : 'Password'}</h3>
            </div>
            {user?.google_id ? (
              <p className="text-slate-400 text-xs">
                {lang === 'fr' ? 'Votre compte est lié à Google. Connectez-vous via Google.' : 'Your account is linked to Google. Sign in via Google.'}
              </p>
            ) : (
              <>
                {pwdMsg && (
                  <div className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs mb-3 ${pwdMsg.type === 'ok' ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>
                    {pwdMsg.type === 'ok' ? <Check size={12} /> : <AlertTriangle size={12} />}
                    {pwdMsg.text}
                  </div>
                )}
                <div className="flex flex-col gap-3">
                  <input
                    type="password"
                    placeholder={lang === 'fr' ? 'Mot de passe actuel' : 'Current password'}
                    value={currentPwd}
                    onChange={e => setCurrentPwd(e.target.value)}
                    className="w-full bg-slate-800/60 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 outline-none focus:border-cyan-500/50 placeholder-slate-600"
                  />
                  <input
                    type="password"
                    placeholder={lang === 'fr' ? 'Nouveau mot de passe' : 'New password'}
                    value={newPwd}
                    onChange={e => setNewPwd(e.target.value)}
                    className="w-full bg-slate-800/60 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 outline-none focus:border-cyan-500/50 placeholder-slate-600"
                  />
                  <input
                    type="password"
                    placeholder={lang === 'fr' ? 'Confirmer le nouveau mot de passe' : 'Confirm new password'}
                    value={confirmPwd}
                    onChange={e => setConfirmPwd(e.target.value)}
                    className="w-full bg-slate-800/60 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 outline-none focus:border-cyan-500/50 placeholder-slate-600"
                  />
                  <button
                    onClick={handleChangePassword}
                    disabled={pwdLoading || !currentPwd || !newPwd || !confirmPwd}
                    className="self-start flex items-center gap-2 bg-cyan-500/15 hover:bg-cyan-500/25 border border-cyan-500/30 text-cyan-400 px-4 py-2 rounded-lg text-xs font-semibold transition disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {pwdLoading ? <RefreshCw size={12} className="animate-spin" /> : <Check size={12} />}
                    {lang === 'fr' ? 'Mettre à jour le mot de passe' : 'Update password'}
                  </button>
                </div>
              </>
            )}
          </div>

          {/* ── 2FA ── */}
          <div className="sku-card rounded-xl p-5">
            <div className="flex items-center gap-3 mb-4">
              <SkuIcon color="#4ade80" size={32}><Shield size={13} className="text-green-300" /></SkuIcon>
              <div>
                <h3 className="text-white font-semibold text-sm">{lang === 'fr' ? 'Double authentification (2FA)' : 'Two-factor authentication (2FA)'}</h3>
                {user?.mfa_enabled && (
                  <span className="inline-flex items-center gap-1 text-xs text-green-400 mt-0.5">
                    <Check size={10} />{lang === 'fr' ? 'Activée' : 'Enabled'}
                  </span>
                )}
              </div>
            </div>

            {mfaMsg && (
              <div className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs mb-3 ${mfaMsg.type === 'ok' ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>
                {mfaMsg.type === 'ok' ? <Check size={12} /> : <AlertTriangle size={12} />}
                {mfaMsg.text}
              </div>
            )}

            {!user?.mfa_enabled && mfaStep === null && (
              <div>
                <p className="text-slate-400 text-xs mb-3">
                  {lang === 'fr'
                    ? 'Protégez votre compte avec une application d\'authentification (Google Authenticator, Authy…).'
                    : 'Protect your account with an authenticator app (Google Authenticator, Authy…).'}
                </p>
                <button
                  onClick={handleMfaSetup}
                  disabled={mfaLoading}
                  className="flex items-center gap-2 bg-green-500/15 hover:bg-green-500/25 border border-green-500/30 text-green-400 px-4 py-2 rounded-lg text-xs font-semibold transition disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {mfaLoading ? <RefreshCw size={12} className="animate-spin" /> : <Shield size={12} />}
                  {lang === 'fr' ? 'Configurer la 2FA' : 'Set up 2FA'}
                </button>
              </div>
            )}

            {!user?.mfa_enabled && mfaStep === 'setup' && (
              <div className="flex flex-col gap-4">
                <p className="text-slate-400 text-xs">
                  {lang === 'fr'
                    ? 'Scannez ce QR code avec votre application d\'authentification, puis entrez le code à 6 chiffres pour confirmer.'
                    : 'Scan this QR code with your authenticator app, then enter the 6-digit code to confirm.'}
                </p>
                {mfaQrCode && (
                  <div className="flex justify-center">
                    <img
                      src={`data:image/png;base64,${mfaQrCode}`}
                      alt="QR 2FA"
                      className="w-36 h-36 rounded-lg border border-slate-700"
                    />
                  </div>
                )}
                {mfaSecret && (
                  <div className="bg-slate-800/60 border border-slate-700 rounded-lg px-3 py-2">
                    <p className="text-slate-500 text-xs mb-1">{lang === 'fr' ? 'Clé manuelle (si QR indisponible) :' : 'Manual key (if QR unavailable):'}</p>
                    <code className="text-cyan-400 text-xs font-mono tracking-widest break-all">{mfaSecret}</code>
                  </div>
                )}
                <input
                  type="text"
                  inputMode="numeric"
                  maxLength={6}
                  placeholder={lang === 'fr' ? 'Code à 6 chiffres' : '6-digit code'}
                  value={mfaCode}
                  onChange={e => setMfaCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  className="w-full bg-slate-800/60 border border-slate-700 text-white text-center text-xl font-mono tracking-widest rounded-lg px-3 py-2 outline-none focus:border-green-500/50 placeholder-slate-600"
                />
                <div className="flex items-center gap-2">
                  <button
                    onClick={handleMfaVerify}
                    disabled={mfaLoading || mfaCode.length !== 6}
                    className="flex items-center gap-2 bg-green-500/15 hover:bg-green-500/25 border border-green-500/30 text-green-400 px-4 py-2 rounded-lg text-xs font-semibold transition disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {mfaLoading ? <RefreshCw size={12} className="animate-spin" /> : <Check size={12} />}
                    {lang === 'fr' ? 'Confirmer' : 'Confirm'}
                  </button>
                  <button
                    onClick={() => { setMfaStep(null); setMfaMsg(null); setMfaCode(''); }}
                    className="text-slate-500 hover:text-slate-300 text-xs transition"
                  >
                    {lang === 'fr' ? 'Annuler' : 'Cancel'}
                  </button>
                </div>
              </div>
            )}

            {user?.mfa_enabled && mfaStep === null && (
              <div>
                <p className="text-slate-400 text-xs mb-3">
                  {lang === 'fr'
                    ? 'La double authentification est activée. Chaque connexion nécessite un code de votre application.'
                    : 'Two-factor authentication is enabled. Every sign-in requires a code from your app.'}
                </p>
                <button
                  onClick={() => { setMfaStep('disabling'); setMfaCode(''); setMfaDisablePwd(''); setMfaMsg(null); }}
                  className="flex items-center gap-2 bg-red-500/15 hover:bg-red-500/25 border border-red-500/30 text-red-400 px-4 py-2 rounded-lg text-xs font-semibold transition"
                >
                  <X size={12} />
                  {lang === 'fr' ? 'Désactiver la 2FA' : 'Disable 2FA'}
                </button>
              </div>
            )}

            {user?.mfa_enabled && mfaStep === 'disabling' && (
              <div className="flex flex-col gap-3">
                <p className="text-slate-400 text-xs">
                  {user?.google_id
                    ? (lang === 'fr'
                        ? 'Confirmez avec votre code TOTP actuel.'
                        : 'Confirm with your current TOTP code.')
                    : (lang === 'fr'
                        ? 'Confirmez avec votre mot de passe et votre code TOTP actuel.'
                        : 'Confirm with your password and current TOTP code.')}
                </p>
                {/* Mot de passe : seulement pour les comptes non-Google */}
                {!user?.google_id && (
                  <input
                    type="password"
                    placeholder={lang === 'fr' ? 'Mot de passe' : 'Password'}
                    value={mfaDisablePwd}
                    onChange={e => setMfaDisablePwd(e.target.value)}
                    className="w-full bg-slate-800/60 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 outline-none focus:border-red-500/50 placeholder-slate-600"
                  />
                )}
                <input
                  type="text"
                  inputMode="numeric"
                  maxLength={6}
                  placeholder={lang === 'fr' ? 'Code TOTP (6 chiffres)' : 'TOTP code (6 digits)'}
                  value={mfaCode}
                  onChange={e => setMfaCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  className="w-full bg-slate-800/60 border border-slate-700 text-white text-center text-xl font-mono tracking-widest rounded-lg px-3 py-2 outline-none focus:border-red-500/50 placeholder-slate-600"
                />
                <div className="flex items-center gap-2">
                  <button
                    onClick={handleMfaDisable}
                    disabled={mfaLoading || (!user?.google_id && !mfaDisablePwd) || mfaCode.length !== 6}
                    className="flex items-center gap-2 bg-red-500/15 hover:bg-red-500/25 border border-red-500/30 text-red-400 px-4 py-2 rounded-lg text-xs font-semibold transition disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {mfaLoading ? <RefreshCw size={12} className="animate-spin" /> : <X size={12} />}
                    {lang === 'fr' ? 'Désactiver' : 'Disable'}
                  </button>
                  <button
                    onClick={() => { setMfaStep(null); setMfaMsg(null); setMfaCode(''); setMfaDisablePwd(''); }}
                    className="text-slate-500 hover:text-slate-300 text-xs transition"
                  >
                    {lang === 'fr' ? 'Annuler' : 'Cancel'}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── BILLING ── */}
      {settingsSection === 'billing' && (
        <div className="flex flex-col gap-4">
          <div className="sku-card rounded-xl p-5">
            <div className="flex items-center gap-3 mb-5">
              <SkuIcon color="#22d3ee" size={32}><CreditCard size={13} className="text-cyan-300" /></SkuIcon>
              <h3 className="text-white font-semibold text-sm">{lang === 'fr' ? 'Abonnement actuel' : 'Current plan'}</h3>
            </div>
            <div className="flex items-center justify-between flex-wrap gap-4">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className={`text-xl font-black tracking-wide ${user?.plan === 'dev' ? 'text-violet-400' : user?.plan === 'pro' ? 'text-purple-400' : user?.plan === 'starter' ? 'text-cyan-400' : 'text-slate-400'}`}>
                    {user?.plan?.toUpperCase() ?? 'FREE'}
                  </span>
                  {isPremium && (
                    <span className="text-xs bg-green-500/15 text-green-400 border border-green-500/30 px-1.5 py-0.5 rounded font-semibold">
                      {lang === 'fr' ? 'Actif' : 'Active'}
                    </span>
                  )}
                </div>
                <p className="text-slate-500 text-xs">
                  {user?.plan === 'dev'
                    ? (lang === 'fr' ? '29,90 € / mois · API + Application Scanning' : '€29.90 / month · API + Application Scanning')
                    : user?.plan === 'pro'
                    ? (lang === 'fr' ? '19,90 € / mois · monitoring illimité' : '€19.90 / month · unlimited monitoring')
                    : user?.plan === 'starter'
                    ? (lang === 'fr' ? '9,90 € / mois · 1 domaine surveillé' : '€9.90 / month · 1 monitored domain')
                    : (lang === 'fr' ? 'Plan gratuit · 1 scan / jour' : 'Free plan · 1 scan / day')}
                </p>
              </div>
              {isPremium && (
                <button
                  onClick={handlePortal}
                  disabled={portalLoading}
                  className="flex items-center gap-2 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 px-4 py-2 rounded-lg text-xs font-semibold transition disabled:opacity-40"
                >
                  {portalLoading ? <RefreshCw size={12} className="animate-spin" /> : <CreditCard size={12} />}
                  {lang === 'fr' ? 'Gérer l\'abonnement' : 'Manage subscription'}
                </button>
              )}
            </div>

            {/* Divider */}
            <div className="border-t border-slate-800 my-5" />

            {/* Plan comparison */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className={`rounded-xl border p-4 ${!isPremium ? 'border-cyan-500/30 bg-cyan-500/5' : 'border-slate-800'}`}>
                <p className="text-slate-300 font-bold text-sm mb-1">Free</p>
                <p className="text-slate-600 text-xs mb-3">{lang === 'fr' ? '0 € / mois' : '€0 / month'}</p>
                <ul className="text-slate-500 text-xs space-y-1">
                  <li>· {lang === 'fr' ? '1 scan / jour' : '1 scan / day'}</li>
                  <li>· {lang === 'fr' ? 'Résultats basiques' : 'Basic results'}</li>
                </ul>
              </div>
              <div className={`rounded-xl border p-4 ${user?.plan === 'starter' ? 'border-cyan-500/30 bg-cyan-500/5' : 'border-slate-800'}`}>
                <p className="text-cyan-400 font-bold text-sm mb-1">Starter</p>
                <p className="text-slate-600 text-xs mb-3">{lang === 'fr' ? '9,90 € / mois' : '€9.90 / month'}</p>
                <ul className="text-slate-500 text-xs space-y-1">
                  <li>· {lang === 'fr' ? '1 domaine surveillé' : '1 monitored domain'}</li>
                  <li>· {lang === 'fr' ? 'Checks avancés' : 'Advanced checks'}</li>
                  <li>· {lang === 'fr' ? 'Rapports PDF' : 'PDF reports'}</li>
                </ul>
              </div>
              <div className={`rounded-xl border p-4 ${user?.plan === 'pro' ? 'border-purple-500/30 bg-purple-500/5' : 'border-slate-800'}`}>
                <p className="text-purple-400 font-bold text-sm mb-1">Pro</p>
                <p className="text-slate-600 text-xs mb-3">{lang === 'fr' ? '19,90 € / mois' : '€19.90 / month'}</p>
                <ul className="text-slate-500 text-xs space-y-1">
                  <li>· {lang === 'fr' ? 'Monitoring illimité' : 'Unlimited monitoring'}</li>
                  <li>· {lang === 'fr' ? 'Webhooks & marque blanche' : 'Webhooks & white-label'}</li>
                </ul>
              </div>
              <div className={`rounded-xl border p-4 ${user?.plan === 'dev' ? 'border-violet-500/30 bg-violet-500/5' : 'border-slate-800'}`}>
                <p className="text-violet-400 font-bold text-sm mb-1">Dev</p>
                <p className="text-slate-600 text-xs mb-3">{lang === 'fr' ? '29,90 € / mois' : '€29.90 / month'}</p>
                <ul className="text-slate-500 text-xs space-y-1">
                  <li>· {lang === 'fr' ? 'Accès API (wsk_)' : 'API access (wsk_)'}</li>
                  <li>· {lang === 'fr' ? 'Application Scanning' : 'Application Scanning'}</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── WHITE-LABEL ── */}
      {settingsSection === 'whitelabel' && (
        <div className="flex flex-col gap-5">
          <div className="rounded-xl border border-cyan-500/20 bg-cyan-500/5 p-5">
            <div className="flex items-center gap-3 mb-1">
              <SkuIcon color="#22d3ee" size={32}><Shield size={13} className="text-cyan-300" /></SkuIcon>
              <h3 className="text-cyan-400 font-semibold text-sm">{lang === 'fr' ? 'Marque blanche — Rapports PDF' : 'White-label — PDF Reports'}</h3>
            </div>
            <p className="text-slate-400 text-xs mb-5">
              {lang === 'fr'
                ? 'Personnalisez les rapports PDF avec le nom et le logo de votre agence. Vos clients verront votre marque, pas Wezea.'
                : 'Customise PDF reports with your agency name and logo. Your clients will see your brand, not Wezea.'}
            </p>

            {wbLoading ? (
              <div className="text-slate-500 text-xs">{lang === 'fr' ? 'Chargement...' : 'Loading...'}</div>
            ) : (
              <div className="flex flex-col gap-4">

                {/* Toggle activer */}
                <label className="flex items-center gap-3 cursor-pointer">
                  <div
                    onClick={() => setWbEnabled(v => !v)}
                    className={`relative w-10 h-5 rounded-full transition-colors ${wbEnabled ? 'bg-cyan-500' : 'bg-slate-700'}`}
                  >
                    <div className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${wbEnabled ? 'translate-x-5' : ''}`} />
                  </div>
                  <span className="text-slate-300 text-sm">
                    {lang === 'fr' ? 'Activer la marque blanche' : 'Enable white-label'}
                  </span>
                </label>

                {/* Nom de l'agence */}
                <div>
                  <label className="text-slate-400 text-xs block mb-1.5">
                    {lang === 'fr' ? 'Nom de l\'agence' : 'Agency name'}
                  </label>
                  <input
                    type="text"
                    value={wbName}
                    onChange={e => setWbName(e.target.value)}
                    maxLength={100}
                    placeholder={lang === 'fr' ? 'Mon Agence IT' : 'My IT Agency'}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white text-sm placeholder-slate-600 focus:outline-none focus:border-cyan-500 transition"
                  />
                </div>

                {/* Couleur principale */}
                <div>
                  <label className="text-slate-400 text-xs block mb-1.5">
                    {lang === 'fr' ? 'Couleur principale' : 'Primary colour'}
                  </label>
                  <div className="flex items-center gap-3">
                    <input
                      type="color"
                      value={wbColor}
                      onChange={e => setWbColor(e.target.value)}
                      className="w-10 h-9 rounded-lg border border-slate-700 bg-slate-800 cursor-pointer p-0.5"
                    />
                    <input
                      type="text"
                      value={wbColor}
                      onChange={e => setWbColor(e.target.value)}
                      maxLength={7}
                      placeholder="#22d3ee"
                      className="flex-1 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white text-sm placeholder-slate-600 focus:outline-none focus:border-cyan-500 transition font-mono"
                    />
                    <div className="w-8 h-8 rounded-lg border border-slate-700 shrink-0" style={{ backgroundColor: wbColor }} />
                  </div>
                </div>

                {/* Upload logo */}
                <div>
                  <label className="text-slate-400 text-xs block mb-1.5">
                    {lang === 'fr' ? 'Logo (PNG, JPG, SVG — max 200 Ko)' : 'Logo (PNG, JPG, SVG — max 200 KB)'}
                  </label>
                  <div className="flex items-center gap-3">
                    {wb?.has_logo && wb.logo_b64 && (
                      <img src={wb.logo_b64} alt="logo" className="h-10 max-w-[100px] object-contain rounded border border-slate-700 bg-slate-800 p-1" />
                    )}
                    <label className="flex items-center gap-2 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg px-3 py-2 text-slate-300 text-xs font-medium cursor-pointer transition">
                      <input
                        type="file"
                        accept="image/png,image/jpeg,image/svg+xml,image/webp"
                        className="hidden"
                        disabled={wbLogoUploading}
                        onChange={async e => {
                          const file = e.target.files?.[0];
                          if (!file) return;
                          setWbLogoUploading(true);
                          setWbMsg(null);
                          try {
                            await uploadWhiteLabelLogo(file);
                            const updated = await getWhiteLabel();
                            setWb(updated);
                            setWbMsg({ type: 'ok', text: lang === 'fr' ? 'Logo uploadé ✓' : 'Logo uploaded ✓' });
                          } catch (err: unknown) {
                            const raw = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
                            const detail = typeof raw === 'string' ? raw : undefined;
                            setWbMsg({ type: 'err', text: detail || (lang === 'fr' ? 'Erreur upload logo' : 'Logo upload error') });
                          } finally {
                            setWbLogoUploading(false);
                          }
                        }}
                      />
                      {wbLogoUploading
                        ? (lang === 'fr' ? 'Upload...' : 'Uploading...')
                        : (lang === 'fr' ? 'Choisir un logo' : 'Choose a logo')}
                    </label>
                    {wb?.has_logo && (
                      <button
                        onClick={async () => {
                          setWbMsg(null);
                          try {
                            await deleteWhiteLabelLogo();
                            setWb(prev => prev ? { ...prev, has_logo: false, logo_b64: null } : null);
                            setWbMsg({ type: 'ok', text: lang === 'fr' ? 'Logo supprimé' : 'Logo deleted' });
                          } catch {
                            setWbMsg({ type: 'err', text: lang === 'fr' ? 'Erreur suppression' : 'Delete error' });
                          }
                        }}
                        className="text-red-400 hover:text-red-300 text-xs transition"
                      >
                        {lang === 'fr' ? 'Supprimer' : 'Delete'}
                      </button>
                    )}
                  </div>
                </div>

                {/* Message feedback */}
                {wbMsg && (
                  <p className={`text-xs ${wbMsg.type === 'ok' ? 'text-emerald-400' : 'text-red-400'}`}>
                    {wbMsg.text}
                  </p>
                )}

                {/* Bouton sauvegarder */}
                <button
                  disabled={wbSaving}
                  onClick={async () => {
                    setWbSaving(true);
                    setWbMsg(null);
                    try {
                      const updated = await updateWhiteLabel({
                        enabled: wbEnabled,
                        company_name: wbName,
                        primary_color: wbColor,
                      });
                      setWb(prev => prev ? { ...prev, ...updated } : updated);
                      setWbMsg({ type: 'ok', text: lang === 'fr' ? 'Paramètres sauvegardés ✓' : 'Settings saved ✓' });
                    } catch {
                      setWbMsg({ type: 'err', text: lang === 'fr' ? 'Erreur lors de la sauvegarde' : 'Save error' });
                    } finally {
                      setWbSaving(false);
                    }
                  }}
                  className="w-full py-2.5 rounded-xl bg-cyan-500 hover:bg-cyan-400 disabled:opacity-50 text-slate-900 text-sm font-bold transition"
                >
                  {wbSaving
                    ? (lang === 'fr' ? 'Sauvegarde...' : 'Saving...')
                    : (lang === 'fr' ? 'Enregistrer les paramètres' : 'Save settings')}
                </button>

              </div>
            )}
          </div>
        </div>
      )}

      {/* ── DANGER ZONE ── */}
      {settingsSection === 'danger' && (
        <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-5">
          <div className="flex items-center gap-3 mb-2">
            <SkuIcon color="#f87171" size={32}><AlertTriangle size={13} className="text-red-300" /></SkuIcon>
            <h3 className="text-red-400 font-semibold text-sm">{lang === 'fr' ? 'Zone dangereuse' : 'Danger zone'}</h3>
          </div>
          <p className="text-slate-400 text-xs mb-5">
            {lang === 'fr'
              ? 'La suppression de votre compte est définitive. Toutes vos données (scans, domaines surveillés) seront effacées conformément au RGPD.'
              : 'Deleting your account is permanent. All your data (scans, monitored domains) will be erased in compliance with GDPR.'}
          </p>
          <button
            onClick={() => setShowDeleteModal(true)}
            className="flex items-center gap-2 bg-red-500/15 hover:bg-red-500/25 border border-red-500/30 text-red-400 px-4 py-2 rounded-lg text-xs font-semibold transition"
          >
            <Trash2 size={12} />
            {lang === 'fr' ? 'Supprimer mon compte' : 'Delete my account'}
          </button>
        </div>
      )}

    </div>
  );
}
