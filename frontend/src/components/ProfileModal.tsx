// ─── ProfileModal — RGPD : édition du profil + suppression de compte ──────────
import { useState, useEffect, FormEvent } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, User, Trash2, Save, AlertTriangle, CheckCircle } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { useLanguage } from '../i18n/LanguageContext';

interface Props {
  open: boolean;
  onClose: () => void;
}

type Tab = 'profile' | 'danger';

export function ProfileModal({ open, onClose }: Props) {
  const { user, updateProfile, deleteAccount } = useAuth();
  const { lang } = useLanguage();

  // ── Profile tab state ──────────────────────────────────────────────────────
  const [firstName, setFirstName] = useState('');
  const [lastName,  setLastName]  = useState('');
  const [saving,    setSaving]    = useState(false);
  const [saveOk,    setSaveOk]    = useState(false);
  const [saveErr,   setSaveErr]   = useState('');

  // ── Delete tab state ───────────────────────────────────────────────────────
  const [delPassword, setDelPassword] = useState('');
  const [delConfirm,  setDelConfirm]  = useState('');
  const [deleting,    setDeleting]    = useState(false);
  const [delErr,      setDelErr]      = useState('');

  // ── Active tab ─────────────────────────────────────────────────────────────
  const [tab, setTab] = useState<Tab>('profile');

  // Sync form with current user data when modal opens
  useEffect(() => {
    if (open && user) {
      setFirstName(user.first_name ?? '');
      setLastName(user.last_name  ?? '');
      setSaveOk(false);
      setSaveErr('');
      setDelPassword('');
      setDelConfirm('');
      setDelErr('');
      setTab('profile');
    }
  }, [open, user]);

  // ── Save profile ───────────────────────────────────────────────────────────
  async function handleSave(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setSaveErr('');
    setSaveOk(false);
    try {
      await updateProfile(firstName.trim() || null, lastName.trim() || null);
      setSaveOk(true);
      setTimeout(() => setSaveOk(false), 3000);
    } catch (err: any) {
      setSaveErr(err?.response?.data?.detail || err?.message || 'Erreur');
    } finally {
      setSaving(false);
    }
  }

  // ── Delete account ─────────────────────────────────────────────────────────
  async function handleDelete(e: FormEvent) {
    e.preventDefault();
    if (delConfirm !== 'SUPPRIMER' && delConfirm !== 'DELETE') {
      setDelErr(lang === 'fr' ? 'Tapez SUPPRIMER pour confirmer' : 'Type DELETE to confirm');
      return;
    }
    setDeleting(true);
    setDelErr('');
    try {
      await deleteAccount(delPassword);
      // logout() is called inside deleteAccount — modal will close as user disappears
    } catch (err: any) {
      setDelErr(err?.response?.data?.detail || err?.message || 'Erreur');
      setDeleting(false);
    }
  }

  if (!open) return null;

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop */}
          <motion.div
            key="backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm"
            onClick={onClose}
          />

          {/* Modal */}
          <motion.div
            key="modal"
            initial={{ opacity: 0, scale: 0.95, y: 16 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 16 }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none"
          >
            <div
              className="w-full max-w-md pointer-events-auto rounded-2xl overflow-hidden"
              style={{
                background: 'linear-gradient(180deg,#0f151e,#0b1018)',
                border: '1px solid rgba(255,255,255,0.08)',
                boxShadow: '0 24px 80px rgba(0,0,0,0.8), 0 1px 0 rgba(255,255,255,0.06) inset',
              }}
            >
              {/* Header */}
              <div
                className="flex items-center justify-between px-6 py-4"
                style={{ borderBottom: '1px solid rgba(255,255,255,0.07)' }}
              >
                <div className="flex items-center gap-3">
                  <div
                    className="p-2 rounded-xl"
                    style={{ background: 'rgba(34,211,238,0.08)', border: '1px solid rgba(34,211,238,0.15)' }}
                  >
                    <User size={16} className="text-cyan-400" />
                  </div>
                  <div>
                    <h2
                      className="text-white font-bold text-base"
                      style={{ fontFamily: 'var(--font-display)', letterSpacing: '-0.02em' }}
                    >
                      {lang === 'fr' ? 'Mon profil' : 'My profile'}
                    </h2>
                    <p className="text-slate-500 text-xs">{user?.email}</p>
                  </div>
                </div>
                <button
                  onClick={onClose}
                  className="text-slate-600 hover:text-slate-300 transition p-1 rounded-lg hover:bg-slate-800"
                >
                  <X size={18} />
                </button>
              </div>

              {/* Tabs */}
              <div
                className="flex"
                style={{ borderBottom: '1px solid rgba(255,255,255,0.07)' }}
              >
                {([['profile', lang === 'fr' ? '👤 Informations' : '👤 Information'],
                   ['danger',  lang === 'fr' ? '⚠️ Supprimer' : '⚠️ Delete account']] as [Tab, string][]).map(([key, label]) => (
                  <button
                    key={key}
                    onClick={() => setTab(key)}
                    className={`flex-1 px-4 py-3 text-xs font-medium transition-all ${
                      tab === key
                        ? key === 'danger'
                          ? 'text-red-400 border-b-2 border-red-500'
                          : 'text-cyan-400 border-b-2 border-cyan-500'
                        : 'text-slate-500 hover:text-slate-300'
                    }`}
                    style={{ marginBottom: '-1px' }}
                  >
                    {label}
                  </button>
                ))}
              </div>

              {/* Body */}
              <div className="p-6">

                {/* ── Profile Tab ─────────────────────────────────────────── */}
                {tab === 'profile' && (
                  <form onSubmit={handleSave} className="flex flex-col gap-4">
                    <p className="text-slate-500 text-xs leading-relaxed">
                      {lang === 'fr'
                        ? 'Ces informations sont facultatives et stockées de façon sécurisée.'
                        : 'This information is optional and stored securely.'}
                    </p>

                    {/* First name */}
                    <div className="flex flex-col gap-1.5">
                      <label className="text-xs font-medium text-slate-400">
                        {lang === 'fr' ? 'Prénom' : 'First name'}
                      </label>
                      <input
                        type="text"
                        value={firstName}
                        onChange={e => setFirstName(e.target.value)}
                        maxLength={100}
                        placeholder={lang === 'fr' ? 'Votre prénom' : 'Your first name'}
                        className="w-full rounded-xl px-4 py-2.5 text-sm text-white placeholder:text-slate-600 focus:outline-none transition"
                        style={{
                          background: 'rgba(255,255,255,0.04)',
                          border: '1px solid rgba(255,255,255,0.08)',
                          boxShadow: '0 2px 6px rgba(0,0,0,0.3) inset',
                        }}
                        onFocus={e => e.currentTarget.style.borderColor = 'rgba(34,211,238,0.4)'}
                        onBlur={e => e.currentTarget.style.borderColor = 'rgba(255,255,255,0.08)'}
                      />
                    </div>

                    {/* Last name */}
                    <div className="flex flex-col gap-1.5">
                      <label className="text-xs font-medium text-slate-400">
                        {lang === 'fr' ? 'Nom' : 'Last name'}
                      </label>
                      <input
                        type="text"
                        value={lastName}
                        onChange={e => setLastName(e.target.value)}
                        maxLength={100}
                        placeholder={lang === 'fr' ? 'Votre nom' : 'Your last name'}
                        className="w-full rounded-xl px-4 py-2.5 text-sm text-white placeholder:text-slate-600 focus:outline-none transition"
                        style={{
                          background: 'rgba(255,255,255,0.04)',
                          border: '1px solid rgba(255,255,255,0.08)',
                          boxShadow: '0 2px 6px rgba(0,0,0,0.3) inset',
                        }}
                        onFocus={e => e.currentTarget.style.borderColor = 'rgba(34,211,238,0.4)'}
                        onBlur={e => e.currentTarget.style.borderColor = 'rgba(255,255,255,0.08)'}
                      />
                    </div>

                    {/* Email (readonly) */}
                    <div className="flex flex-col gap-1.5">
                      <label className="text-xs font-medium text-slate-400">Email</label>
                      <div
                        className="w-full rounded-xl px-4 py-2.5 text-sm text-slate-500 font-mono"
                        style={{
                          background: 'rgba(0,0,0,0.25)',
                          border: '1px solid rgba(255,255,255,0.05)',
                        }}
                      >
                        {user?.email}
                      </div>
                    </div>

                    {/* Feedback */}
                    {saveErr && (
                      <p className="text-red-400 text-xs flex items-center gap-1.5">
                        <AlertTriangle size={13} />{saveErr}
                      </p>
                    )}
                    {saveOk && (
                      <p className="text-emerald-400 text-xs flex items-center gap-1.5">
                        <CheckCircle size={13} />
                        {lang === 'fr' ? 'Profil mis à jour ✓' : 'Profile updated ✓'}
                      </p>
                    )}

                    {/* Submit */}
                    <button
                      type="submit"
                      disabled={saving}
                      className="sku-btn-primary flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm w-full disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none"
                    >
                      {saving ? (
                        <div className="w-4 h-4 border-2 border-white/20 border-t-white rounded-full animate-spin" />
                      ) : (
                        <Save size={15} />
                      )}
                      {lang === 'fr' ? 'Enregistrer' : 'Save changes'}
                    </button>
                  </form>
                )}

                {/* ── Danger Tab ──────────────────────────────────────────── */}
                {tab === 'danger' && (
                  <form onSubmit={handleDelete} className="flex flex-col gap-4">
                    {/* Warning box */}
                    <div
                      className="rounded-xl p-4 flex gap-3"
                      style={{
                        background: 'rgba(239,68,68,0.07)',
                        border: '1px solid rgba(239,68,68,0.2)',
                      }}
                    >
                      <AlertTriangle size={16} className="text-red-400 shrink-0 mt-0.5" />
                      <div>
                        <p className="text-red-400 text-xs font-medium mb-1">
                          {lang === 'fr' ? 'Action irréversible' : 'Irreversible action'}
                        </p>
                        <p className="text-slate-400 text-xs leading-relaxed">
                          {lang === 'fr'
                            ? 'La suppression de votre compte effacera définitivement toutes vos données, y compris l\'historique de scans. Cette action ne peut pas être annulée.'
                            : 'Deleting your account will permanently erase all your data, including scan history. This action cannot be undone.'}
                        </p>
                      </div>
                    </div>

                    {/* Password confirmation */}
                    <div className="flex flex-col gap-1.5">
                      <label className="text-xs font-medium text-slate-400">
                        {lang === 'fr' ? 'Mot de passe actuel' : 'Current password'}
                      </label>
                      <input
                        type="password"
                        value={delPassword}
                        onChange={e => setDelPassword(e.target.value)}
                        required
                        placeholder="••••••••"
                        className="w-full rounded-xl px-4 py-2.5 text-sm text-white placeholder:text-slate-600 focus:outline-none transition"
                        style={{
                          background: 'rgba(255,255,255,0.04)',
                          border: '1px solid rgba(255,255,255,0.08)',
                          boxShadow: '0 2px 6px rgba(0,0,0,0.3) inset',
                        }}
                        onFocus={e => e.currentTarget.style.borderColor = 'rgba(239,68,68,0.4)'}
                        onBlur={e => e.currentTarget.style.borderColor = 'rgba(255,255,255,0.08)'}
                      />
                    </div>

                    {/* Type confirmation */}
                    <div className="flex flex-col gap-1.5">
                      <label className="text-xs font-medium text-slate-400">
                        {lang === 'fr'
                          ? 'Tapez SUPPRIMER pour confirmer'
                          : 'Type DELETE to confirm'}
                      </label>
                      <input
                        type="text"
                        value={delConfirm}
                        onChange={e => setDelConfirm(e.target.value)}
                        required
                        placeholder={lang === 'fr' ? 'SUPPRIMER' : 'DELETE'}
                        className="w-full rounded-xl px-4 py-2.5 text-sm text-white placeholder:text-slate-600 focus:outline-none transition font-mono tracking-wider"
                        style={{
                          background: 'rgba(255,255,255,0.04)',
                          border: '1px solid rgba(255,255,255,0.08)',
                          boxShadow: '0 2px 6px rgba(0,0,0,0.3) inset',
                        }}
                        onFocus={e => e.currentTarget.style.borderColor = 'rgba(239,68,68,0.4)'}
                        onBlur={e => e.currentTarget.style.borderColor = 'rgba(255,255,255,0.08)'}
                      />
                    </div>

                    {/* Error */}
                    {delErr && (
                      <p className="text-red-400 text-xs flex items-center gap-1.5">
                        <AlertTriangle size={13} />{delErr}
                      </p>
                    )}

                    {/* Submit */}
                    <button
                      type="submit"
                      disabled={deleting || !delPassword || (delConfirm !== 'SUPPRIMER' && delConfirm !== 'DELETE')}
                      className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm w-full font-medium transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                      style={{
                        background: deleting ? 'rgba(239,68,68,0.3)' : 'rgba(239,68,68,0.15)',
                        border: '1px solid rgba(239,68,68,0.3)',
                        color: '#f87171',
                        boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
                      }}
                    >
                      {deleting ? (
                        <div className="w-4 h-4 border-2 border-red-400/30 border-t-red-400 rounded-full animate-spin" />
                      ) : (
                        <Trash2 size={15} />
                      )}
                      {lang === 'fr' ? 'Supprimer mon compte' : 'Delete my account'}
                    </button>
                  </form>
                )}

              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
