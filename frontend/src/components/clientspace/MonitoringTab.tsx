// ─── MonitoringTab — Extracted from ClientSpace.tsx ──────────────────────────
import React from 'react';
import { motion } from 'framer-motion';
import {
  Globe, Plus, Trash2, RefreshCw, X, Check, Bell,
} from 'lucide-react';
import { apiClient } from '../../lib/api';
import type { MonitoredDomain, ScanHistoryItem } from './types';
import { CHECK_LABELS } from './types';
import { scoreColor, RiskBadge, Sparkline } from './helpers';

// ─────────────────────────────────────────────────────────────────────────────
// Props
// ─────────────────────────────────────────────────────────────────────────────

interface Props {
  domains: MonitoredDomain[];
  isPremium: boolean;
  planLimit: number | null;
  userPlan: string | undefined;
  newDomain: string;
  setNewDomain: (v: string) => void;
  addError: string;
  setAddError: (v: string) => void;
  addLoading: boolean;
  newDomainChecks: Record<string, boolean>;
  setNewDomainChecks: React.Dispatch<React.SetStateAction<Record<string, boolean>>>;
  newDomainFrequency: 'weekly' | 'biweekly' | 'monthly';
  setNewDomainFrequency: (v: 'weekly' | 'biweekly' | 'monthly') => void;
  newDomainEmailReport: boolean;
  setNewDomainEmailReport: (v: boolean) => void;
  editingThreshold: string | null;
  setEditingThreshold: (v: string | null) => void;
  thresholdValue: number;
  setThresholdValue: (v: number) => void;
  pendingChecks: Record<string, Record<string, boolean>>;
  checksLoading: string | null;
  scanningDomain: string | null;
  scanDoneMap: Record<string, boolean>;
  historyByDomain: Record<string, ScanHistoryItem[]>;
  addDomain: () => void;
  removeDomain: (domain: string) => void;
  scanDomainNow: (domain: string) => void;
  saveThreshold: (domain: string) => void;
  toggleCheck: (d: MonitoredDomain, key: string) => void;
  setDomains: React.Dispatch<React.SetStateAction<MonitoredDomain[]>>;
  setPricingModalOpen: (v: boolean) => void;
  lang: 'fr' | 'en';
}

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

export default function MonitoringTab({
  domains,
  isPremium: _isPremium,
  planLimit,
  userPlan,
  newDomain,
  setNewDomain,
  addError,
  setAddError,
  addLoading,
  newDomainChecks,
  setNewDomainChecks,
  newDomainFrequency,
  setNewDomainFrequency,
  newDomainEmailReport,
  setNewDomainEmailReport,
  editingThreshold,
  setEditingThreshold,
  thresholdValue,
  setThresholdValue,
  pendingChecks,
  checksLoading,
  scanningDomain,
  scanDoneMap,
  historyByDomain,
  addDomain,
  removeDomain,
  scanDomainNow,
  saveThreshold,
  toggleCheck,
  setDomains,
  setPricingModalOpen,
  lang,
}: Props) {
  return (
                <div className="flex flex-col gap-5">

                  {/* Add domain */}
                  <div className="sku-card rounded-xl p-5">
                    <div className="flex items-center justify-between mb-4">
                      <div>
                        <p className="text-white font-bold text-sm flex items-center gap-2">
                          <Plus size={14} className="text-cyan-400" />
                          {lang === 'fr' ? 'Ajouter un domaine' : 'Add a domain'}
                        </p>
                        <p className="text-slate-500 text-xs mt-0.5">
                          {domains.length}/{planLimit !== null ? planLimit : '\u221e'} {lang === 'fr' ? 'domaine' : 'domain'}{domains.length !== 1 ? (lang === 'fr' ? 's' : 's') : ''} {lang === 'fr' ? 'utilisé' : 'used'}{domains.length !== 1 ? (lang === 'fr' ? 's' : '') : ''}
                        </p>
                      </div>
                      {planLimit !== null && domains.length >= planLimit && (
                        <span className="text-xs text-orange-400 font-mono bg-orange-500/10 border border-orange-500/20 px-2 py-1 rounded-lg">
                          {lang === 'fr' ? 'Limite atteinte' : 'Limit reached'}
                        </span>
                      )}
                    </div>
                    <div className="flex flex-col gap-4">
                      {/* Row 1: Domain input + Add button */}
                      <div className="flex gap-2 flex-wrap">
                        <input
                          type="text"
                          placeholder="exemple.com"
                          value={newDomain}
                          onChange={e => { setNewDomain(e.target.value); setAddError(''); }}
                          onKeyDown={e => e.key === 'Enter' && addDomain()}
                          disabled={planLimit !== null && domains.length >= planLimit}
                          className="flex-1 min-w-[220px] bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white font-mono focus:outline-none focus:border-cyan-500 transition placeholder:text-slate-600 disabled:opacity-40"
                        />
                        <button
                          onClick={addDomain}
                          disabled={addLoading || !newDomain.trim() || (planLimit !== null && domains.length >= planLimit)}
                          className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 hover:bg-cyan-500/30 transition text-sm font-semibold disabled:opacity-40"
                        >
                          {addLoading
                            ? <div className="w-3.5 h-3.5 border-2 border-cyan-400/30 border-t-cyan-400 rounded-full animate-spin" />
                            : <Plus size={14} />
                          }
                          {lang === 'fr' ? 'Ajouter' : 'Add'}
                        </button>
                      </div>
                      {/* Row 2: Checks + Planification config */}
                      <div className="border border-slate-800 rounded-xl p-4 flex flex-col gap-4 bg-slate-800/20">
                        <p className="text-[10px] font-mono text-slate-500 uppercase tracking-widest">
                          {lang === 'fr' ? 'Configuration du monitoring' : 'Monitoring configuration'}
                        </p>
                        {/* Checks */}
                        <div className="flex flex-col gap-2">
                          <p className="text-xs text-slate-400 font-medium">{lang === 'fr' ? 'Checks à effectuer' : 'Checks to run'}</p>
                          <div className="flex gap-1.5 flex-wrap">
                            {CHECK_LABELS.map(({ key, label }) => {
                              const enabled = newDomainChecks[key] !== false;
                              return (
                                <button
                                  key={key}
                                  type="button"
                                  onClick={() => setNewDomainChecks(prev => ({ ...prev, [key]: !enabled }))}
                                  className={`
                                    text-[10px] font-mono px-2.5 py-1 rounded-md border transition-all
                                    ${enabled
                                      ? 'bg-cyan-500/10 text-cyan-400 border-cyan-500/30 hover:bg-cyan-500/20'
                                      : 'bg-slate-900 text-slate-600 border-slate-700 hover:border-slate-600'}
                                  `}
                                >
                                  {label}
                                </button>
                              );
                            })}
                          </div>
                        </div>
                        {/* Planification */}
                        <div className="flex items-end gap-6 flex-wrap">
                          <div className="flex flex-col gap-1.5">
                            <p className="text-xs text-slate-400 font-medium">{lang === 'fr' ? 'Fréquence de scan' : 'Scan frequency'}</p>
                            <select
                              value={newDomainFrequency}
                              onChange={e => setNewDomainFrequency(e.target.value as 'weekly' | 'biweekly' | 'monthly')}
                              className="bg-slate-800 border border-slate-700 text-slate-300 text-xs font-mono rounded-md px-2.5 py-1.5 focus:outline-none focus:border-cyan-500/50 cursor-pointer hover:border-slate-600 transition"
                            >
                              <option value="weekly">{lang === 'fr' ? 'Hebdomadaire' : 'Weekly'}</option>
                              <option value="biweekly">{lang === 'fr' ? 'Bimensuel' : 'Biweekly'}</option>
                              <option value="monthly">{lang === 'fr' ? 'Mensuel' : 'Monthly'}</option>
                            </select>
                          </div>
                          <label className="flex items-center gap-2 cursor-pointer pb-1">
                            <input
                              type="checkbox"
                              checked={newDomainEmailReport}
                              onChange={e => setNewDomainEmailReport(e.target.checked)}
                              className="w-3.5 h-3.5 accent-cyan-400 cursor-pointer"
                            />
                            <span className="text-xs font-mono text-slate-400 hover:text-slate-300 transition">
                              {lang === 'fr' ? 'Rapport PDF par email' : 'PDF report by email'}
                            </span>
                          </label>
                        </div>
                      </div>
                    </div>
                    {addError && (
                      <p className="mt-2 text-red-400 text-xs font-mono bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-1.5">
                        {addError}
                      </p>
                    )}
                  </div>

                  {/* Upsell banner — Starter avec 1 domaine (limite atteinte) */}
                  {userPlan === 'starter' && domains.length >= 1 && (
                    <motion.div
                      initial={{ opacity: 0, y: -6 }}
                      animate={{ opacity: 1, y: 0 }}
                      className={`rounded-xl border p-4 flex flex-col sm:flex-row items-start sm:items-center gap-3 ${
                        domains.length >= 1
                          ? 'border-orange-500/30 bg-orange-500/5'
                          : 'border-purple-500/30 bg-purple-500/5'
                      }`}
                    >
                      <div className="flex-1 min-w-0">
                        <p className="text-orange-300 font-bold text-sm">
                          {lang === 'fr' ? '\u26a0 Limite Starter atteinte' : '\u26a0 Starter limit reached'}
                        </p>
                        <p className="text-slate-400 text-xs mt-0.5">
                          {lang === 'fr'
                            ? 'Passez Pro pour surveiller des domaines en illimit\u00e9, acc\u00e9der aux webhooks et d\u00e9bloquer toutes les fonctionnalit\u00e9s.'
                            : 'Upgrade to Pro to monitor unlimited domains, access webhooks and unlock all features.'}
                        </p>
                      </div>
                      <button
                        onClick={() => setPricingModalOpen(true)}
                        className="shrink-0 flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold transition bg-orange-500/20 text-orange-300 border border-orange-500/30 hover:bg-orange-500/30"
                      >
                        {lang === 'fr' ? 'Passer Pro \u2192' : 'Upgrade to Pro \u2192'}
                      </button>
                    </motion.div>
                  )}

                  {/* Domains table */}
                  {domains.length === 0 ? (
                    <div className="py-16 text-center text-slate-600 text-sm">
                      {lang === 'fr' ? 'Ajoutez votre premier domaine ci-dessus pour commencer.' : 'Add your first domain above to get started.'}
                    </div>
                  ) : (
                    <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
                      <div className="px-5 py-3 border-b border-slate-800 flex items-center justify-between">
                        <p className="text-white font-bold text-sm">{domains.length} {lang === 'fr' ? 'domaine' : 'domain'}{domains.length !== 1 ? (lang === 'fr' ? 's' : 's') : ''} {lang === 'fr' ? 'surveill\u00e9' : 'monitored'}{domains.length !== 1 ? (lang === 'fr' ? 's' : '') : ''}</p>
                        <p className="text-slate-600 text-xs font-mono">{lang === 'fr' ? 'Fr\u00e9quence configurable par domaine' : 'Configurable frequency per domain'}</p>
                      </div>
                      <div className="overflow-x-auto">
                        <table className="w-full">
                          <thead>
                            <tr className="border-b border-slate-800">
                              <th className="px-5 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">{lang === 'fr' ? 'Domaine' : 'Domain'}</th>
                              <th className="px-4 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">{lang === 'fr' ? 'Score' : 'Score'}</th>
                              <th className="px-4 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">{lang === 'fr' ? 'Tendance' : 'Trend'}</th>
                              <th className="px-4 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">{lang === 'fr' ? 'Risque' : 'Risk'}</th>
                              <th className="px-4 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">{lang === 'fr' ? 'Dernier scan' : 'Last scan'}</th>
                              <th className="px-4 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">{lang === 'fr' ? 'Seuil alerte' : 'Alert threshold'}</th>
                              <th className="px-4 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">Checks</th>
                              <th className="px-4 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">{lang === 'fr' ? 'Planification' : 'Schedule'}</th>
                              <th className="px-4 py-3 text-xs font-mono text-slate-500 uppercase tracking-wider" />
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-800/50">
                            {domains.map(d => (
                              <tr key={d.domain} className="hover:bg-slate-800/30 transition-colors group">

                                {/* Domain */}
                                <td className="px-5 py-4">
                                  <div className="flex items-center gap-2">
                                    <Globe size={12} className="text-slate-500 shrink-0" />
                                    <span className="text-white font-mono font-medium text-sm">{d.domain}</span>
                                  </div>
                                </td>

                                {/* Score */}
                                <td className="px-4 py-4">
                                  <span className={`text-xl font-black font-mono ${scoreColor(d.last_score)}`}>
                                    {d.last_score ?? '\u2014'}
                                  </span>
                                </td>

                                {/* Tendance sparkline */}
                                <td className="px-4 py-4">
                                  {(() => {
                                    const scores = [...(historyByDomain[d.domain] ?? [])]
                                      .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
                                      .map(s => s.security_score);
                                    return <Sparkline scores={scores} width={80} height={28} />;
                                  })()}
                                </td>

                                {/* Risk */}
                                <td className="px-4 py-4">
                                  <RiskBadge level={d.last_risk_level} />
                                </td>

                                {/* Last scan */}
                                <td className="px-4 py-4 text-slate-500 text-xs font-mono">
                                  {d.last_scan_at
                                    ? new Date(d.last_scan_at).toLocaleDateString(lang === 'fr' ? 'fr-FR' : 'en-GB', { day: '2-digit', month: '2-digit', year: 'numeric' })
                                    : '\u2014'}
                                </td>

                                {/* Threshold — éditable inline */}
                                <td className="px-4 py-4">
                                  {editingThreshold === d.domain ? (
                                    <div className="flex items-center gap-1.5">
                                      <input
                                        type="number"
                                        min={1} max={50}
                                        value={thresholdValue}
                                        onChange={e => setThresholdValue(Number(e.target.value))}
                                        className="w-14 bg-slate-800 border border-cyan-500/40 rounded px-2 py-1 text-xs text-white font-mono focus:outline-none text-center"
                                        autoFocus
                                      />
                                      <span className="text-slate-600 text-xs">pts</span>
                                      <button
                                        onClick={() => saveThreshold(d.domain)}
                                        className="p-1 rounded text-green-400 hover:bg-green-500/10 transition"
                                        title={lang === 'fr' ? 'Sauvegarder' : 'Save'}
                                      >
                                        <Check size={13} />
                                      </button>
                                      <button
                                        onClick={() => setEditingThreshold(null)}
                                        className="p-1 rounded text-slate-600 hover:text-slate-400 transition"
                                        title={lang === 'fr' ? 'Annuler' : 'Cancel'}
                                      >
                                        <X size={13} />
                                      </button>
                                    </div>
                                  ) : (
                                    <button
                                      onClick={() => { setEditingThreshold(d.domain); setThresholdValue(d.alert_threshold); }}
                                      className="flex items-center gap-1.5 text-xs font-mono text-slate-400 hover:text-white transition group-hover:opacity-100"
                                      title={lang === 'fr' ? 'Modifier le seuil' : 'Edit threshold'}
                                    >
                                      <Bell size={11} className="text-slate-600" />
                                      −{d.alert_threshold} pts
                                    </button>
                                  )}
                                </td>

                                {/* Checks — toggles interactifs */}
                                <td className="px-4 py-4">
                                  <div className="flex gap-1 flex-wrap">
                                    {CHECK_LABELS.map(({ key, label }) => {
                                      const cfg = pendingChecks[d.domain] ?? d.checks_config;
                                      const enabled = cfg[key] !== false;
                                      const isLoading = checksLoading === d.domain + ':' + key;
                                      return (
                                        <button
                                          key={key}
                                          onClick={() => toggleCheck(d, key)}
                                          disabled={isLoading}
                                          title={enabled ? (lang === 'fr' ? `D\u00e9sactiver le check ${label}` : `Disable check ${label}`) : (lang === 'fr' ? `Activer le check ${label}` : `Enable check ${label}`)}
                                          className={`
                                            text-[9px] font-mono px-1.5 py-0.5 rounded border transition-all
                                            ${enabled
                                              ? 'bg-cyan-500/10 text-cyan-400 border-cyan-500/30 hover:bg-cyan-500/20'
                                              : 'bg-slate-900 text-slate-600 border-slate-800 hover:border-slate-700'}
                                            disabled:opacity-40
                                          `}
                                        >
                                          {label}
                                        </button>
                                      );
                                    })}
                                  </div>
                                  <p className="text-xs text-slate-500 mt-1.5">{lang === 'fr' ? 'Cliquer pour activer / d\u00e9sactiver' : 'Click to enable / disable'}</p>
                                </td>

                                {/* Planification + Alertes — Feature 3 & 4 */}
                                <td className="px-4 py-4">
                                  <div className="flex flex-col gap-2">
                                    {/* Fréquence de scan */}
                                    <select
                                      value={d.scan_frequency}
                                      onChange={async e => {
                                        const freq = e.target.value as 'weekly' | 'biweekly' | 'monthly';
                                        setDomains(prev => prev.map(x => x.domain === d.domain ? { ...x, scan_frequency: freq } : x));
                                        try { await apiClient.patch(`/monitoring/domains/${d.domain}`, { scan_frequency: freq }); }
                                        catch { /* silently ignore */ }
                                      }}
                                      className="bg-slate-800 border border-slate-700 text-slate-300 text-[10px] font-mono rounded px-1.5 py-1 focus:outline-none focus:border-cyan-500/50 cursor-pointer hover:border-slate-600 transition"
                                      title={lang === 'fr' ? 'Fr\u00e9quence de scan' : 'Scan frequency'}
                                    >
                                      <option value="weekly">{lang === 'fr' ? 'Hebdo' : 'Weekly'}</option>
                                      <option value="biweekly">{lang === 'fr' ? 'Bimensuel' : 'Biweekly'}</option>
                                      <option value="monthly">{lang === 'fr' ? 'Mensuel' : 'Monthly'}</option>
                                    </select>

                                    {/* Seuil SSL — Feature 4 */}
                                    <select
                                      value={d.ssl_alert_days ?? 30}
                                      onChange={async e => {
                                        const days = Number(e.target.value);
                                        setDomains(prev => prev.map(x => x.domain === d.domain ? { ...x, ssl_alert_days: days } : x));
                                        try { await apiClient.patch(`/monitoring/domains/${d.domain}`, { ssl_alert_days: days }); }
                                        catch { /* silently ignore */ }
                                      }}
                                      className="bg-slate-800 border border-slate-700 text-slate-300 text-[10px] font-mono rounded px-1.5 py-1 focus:outline-none focus:border-cyan-500/50 cursor-pointer hover:border-slate-600 transition"
                                      title={lang === 'fr' ? "Seuil d'alerte SSL" : 'SSL alert threshold'}
                                    >
                                      <option value={7}>{lang === 'fr' ? 'SSL < 7j' : 'SSL < 7d'}</option>
                                      <option value={14}>{lang === 'fr' ? 'SSL < 14j' : 'SSL < 14d'}</option>
                                      <option value={30}>{lang === 'fr' ? 'SSL < 30j' : 'SSL < 30d'}</option>
                                      <option value={60}>{lang === 'fr' ? 'SSL < 60j' : 'SSL < 60d'}</option>
                                    </select>

                                    {/* Email rapport PDF */}
                                    <label className="flex items-center gap-1.5 cursor-pointer group/pdf">
                                      <input
                                        type="checkbox"
                                        checked={d.email_report}
                                        onChange={async e => {
                                          const val = e.target.checked;
                                          setDomains(prev => prev.map(x => x.domain === d.domain ? { ...x, email_report: val } : x));
                                          try { await apiClient.patch(`/monitoring/domains/${d.domain}`, { email_report: val }); }
                                          catch { /* silently ignore */ }
                                        }}
                                        className="w-3 h-3 accent-cyan-400 cursor-pointer"
                                      />
                                      <span className="text-[10px] font-mono text-slate-500 group-hover/pdf:text-slate-400 transition">
                                        {lang === 'fr' ? 'PDF par email' : 'PDF by email'}
                                      </span>
                                    </label>

                                    {/* Types d'alertes — Feature 4 */}
                                    <details className="group/alerts">
                                      <summary className="text-[10px] font-mono text-slate-600 hover:text-slate-400 cursor-pointer list-none flex items-center gap-1 transition">
                                        <span className="group-open/alerts:rotate-90 transition-transform inline-block">{'\u25b6'}</span>
                                        {lang === 'fr' ? "Types d'alertes" : 'Alert types'}
                                      </summary>
                                      <div className="mt-1.5 flex flex-col gap-1 pl-2">
                                        {([
                                          { key: 'score_drop',        label: lang === 'fr' ? 'Chute de score'          : 'Score drop'        },
                                          { key: 'critical_findings', label: lang === 'fr' ? 'Vuln\u00e9rabilit\u00e9s critiques' : 'Critical findings'  },
                                          { key: 'ssl_expiry',        label: lang === 'fr' ? 'Expiration SSL'          : 'SSL expiry'        },
                                          { key: 'port_changes',      label: lang === 'fr' ? 'Nouveaux ports'         : 'Port changes'      },
                                          { key: 'tech_changes',      label: lang === 'fr' ? 'Changements de version' : 'Version changes'   },
                                        ] as const).map(({ key, label }) => {
                                          const cfg = d.alert_config_parsed ?? {};
                                          const enabled = (cfg as Record<string, boolean>)[key] !== false;
                                          return (
                                            <label key={key} className="flex items-center gap-1.5 cursor-pointer group/al">
                                              <input
                                                type="checkbox"
                                                checked={enabled}
                                                onChange={async e => {
                                                  const val = e.target.checked;
                                                  const newCfg = { ...cfg, [key]: val };
                                                  setDomains(prev => prev.map(x =>
                                                    x.domain === d.domain
                                                      ? { ...x, alert_config_parsed: { ...x.alert_config_parsed, [key]: val } }
                                                      : x
                                                  ));
                                                  try { await apiClient.patch(`/monitoring/domains/${d.domain}`, { alert_config: newCfg }); }
                                                  catch { /* silently ignore */ }
                                                }}
                                                className="w-3 h-3 accent-cyan-400 cursor-pointer"
                                              />
                                              <span className="text-[10px] font-mono text-slate-500 group-hover/al:text-slate-400 transition">
                                                {label}
                                              </span>
                                            </label>
                                          );
                                        })}
                                      </div>
                                    </details>
                                  </div>
                                </td>

                                {/* Actions — Scan Now + Delete */}
                                <td className="px-4 py-4 text-right">
                                  <div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                    {/* Scan maintenant */}
                                    <button
                                      onClick={() => scanDomainNow(d.domain)}
                                      disabled={!!scanningDomain}
                                      title={lang === 'fr' ? 'Lancer un scan imm\u00e9diat' : 'Run an immediate scan'}
                                      className={`p-1.5 rounded-lg transition ${
                                        scanDoneMap[d.domain]
                                          ? 'text-green-400 bg-green-500/10'
                                          : 'text-slate-500 hover:text-cyan-400 hover:bg-cyan-500/10'
                                      } disabled:opacity-40 disabled:cursor-not-allowed`}
                                    >
                                      {scanningDomain === d.domain
                                        ? <RefreshCw size={13} className="animate-spin" />
                                        : scanDoneMap[d.domain]
                                          ? <Check size={13} />
                                          : <RefreshCw size={13} />}
                                    </button>
                                    {/* Supprimer */}
                                    <button
                                      onClick={() => removeDomain(d.domain)}
                                      className="p-1.5 rounded-lg text-slate-700 hover:text-red-400 hover:bg-red-500/10 transition"
                                      title={lang === 'fr' ? 'Retirer du monitoring' : 'Remove from monitoring'}
                                    >
                                      <Trash2 size={13} />
                                    </button>
                                  </div>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  <p className="text-center text-[11px] text-slate-700 font-mono">
                    {lang === 'fr' ? 'Alerte email automatique si le score baisse du seuil configur\u00e9 \u00b7 Fr\u00e9quence configurable par domaine' : 'Automatic email alert if score drops below configured threshold \u00b7 Configurable frequency per domain'}
                  </p>
                </div>
  );
}
