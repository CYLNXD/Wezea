import React from 'react';
import {
  AppWindow, Plus, CheckCircle2, AlertTriangle, FileText,
  ScanSearch, ChevronUp, ChevronDown, Trash2, Check,
} from 'lucide-react';
import SkuIcon from '../SkuIcon';
import { scoreColor } from './helpers';
import type { VerifiedApp, AppScanFinding, DastDetails, SecretDetails } from './types';

interface Props {
  apps: VerifiedApp[];
  appNewName: string;
  setAppNewName: (v: string) => void;
  appNewUrl: string;
  setAppNewUrl: (v: string) => void;
  appNewMethod: 'dns' | 'file';
  setAppNewMethod: (v: 'dns' | 'file') => void;
  appAddLoading: boolean;
  appAddError: string;
  appVerifyLoading: number | null;
  appVerifyMsg: Record<number, { ok: boolean; msg: string }>;
  appScanLoading: number | null;
  appScanResults: Record<number, AppScanFinding[]>;
  appScanDetails: Record<number, { dast?: DastDetails; secrets?: SecretDetails }>;
  appExpandedId: number | null;
  setAppExpandedId: (v: number | null) => void;
  appVerifyInfo: Record<number, boolean>;
  setAppVerifyInfo: React.Dispatch<React.SetStateAction<Record<number, boolean>>>;
  handleAddApp: () => void;
  handleDeleteApp: (id: number) => void;
  handleVerifyApp: (id: number) => void;
  handleScanApp: (id: number) => void;
  lang: 'fr' | 'en';
  setAppAddError: (v: string) => void;
}

export default function AppsTab({
  apps, appNewName, setAppNewName, appNewUrl, setAppNewUrl,
  appNewMethod, setAppNewMethod, appAddLoading, appAddError,
  appVerifyLoading, appVerifyMsg, appScanLoading, appScanResults,
  appScanDetails, appExpandedId, setAppExpandedId, appVerifyInfo,
  setAppVerifyInfo, handleAddApp, handleDeleteApp, handleVerifyApp,
  handleScanApp, lang, setAppAddError,
}: Props) {
  return (
    <div className="flex flex-col gap-5">

      {/* ── Add application ──────────────────────────────────── */}
      <div className="sku-card rounded-xl p-5">
        <div className="flex items-center gap-3 mb-4">
          <SkuIcon color="#a78bfa" size={36}>
            <AppWindow size={16} className="text-violet-300" />
          </SkuIcon>
          <div>
            <p className="text-white font-bold text-sm">
              {lang === 'fr' ? 'Ajouter une application' : 'Add an application'}
            </p>
            <p className="text-slate-500 text-xs">
              {lang === 'fr'
                ? 'Scannez vos applications web custom pour détecter les vulnérabilités'
                : 'Scan your custom web apps to detect vulnerabilities'}
            </p>
          </div>
        </div>

        <div className="flex flex-col gap-3">
          <div className="flex gap-2 flex-wrap">
            <input
              type="text"
              placeholder={lang === 'fr' ? 'Nom (ex: Mon App)' : 'Name (e.g. My App)'}
              value={appNewName}
              onChange={e => setAppNewName(e.target.value)}
              className="flex-1 min-w-[160px] sku-inset rounded-lg px-3 py-2 text-sm text-white font-mono focus:outline-none focus:border-violet-500 transition placeholder:text-slate-600"
            />
            <input
              type="text"
              placeholder="https://monapp.exemple.com"
              value={appNewUrl}
              onChange={e => { setAppNewUrl(e.target.value); setAppAddError(''); }}
              onKeyDown={e => e.key === 'Enter' && handleAddApp()}
              className="flex-1 min-w-[220px] sku-inset rounded-lg px-3 py-2 text-sm text-white font-mono focus:outline-none focus:border-violet-500 transition placeholder:text-slate-600"
            />
          </div>
          {/* Méthode de vérification */}
          <div className="flex gap-2 items-center flex-wrap">
            <span className="text-slate-500 text-xs">{lang === 'fr' ? 'Vérification :' : 'Ownership check:'}</span>
            {(['dns', 'file'] as const).map(m => (
              <button
                key={m}
                type="button"
                onClick={() => setAppNewMethod(m)}
                className={`text-xs font-mono px-3 py-1 rounded-md border transition-all ${
                  appNewMethod === m
                    ? 'bg-violet-500/15 text-violet-300 border-violet-500/30'
                    : 'bg-slate-900 text-slate-500 border-slate-700 hover:border-slate-600'
                }`}
              >
                {m === 'dns' ? '\u{1F4E1} DNS TXT' : '\u{1F4C4} Fichier .well-known'}
              </button>
            ))}
            <button
              onClick={handleAddApp}
              disabled={appAddLoading || !appNewName.trim() || !appNewUrl.trim()}
              className="ml-auto flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-violet-500/20 text-violet-300 border border-violet-500/30 hover:bg-violet-500/30 transition text-sm font-semibold disabled:opacity-40"
            >
              {appAddLoading
                ? <div className="w-3.5 h-3.5 border-2 border-violet-400/30 border-t-violet-400 rounded-full animate-spin" />
                : <Plus size={14} />
              }
              {lang === 'fr' ? 'Ajouter' : 'Add'}
            </button>
          </div>
          {appAddError && <p className="text-red-400 text-xs">{appAddError}</p>}
        </div>
      </div>

      {/* ── Liste des applications ────────────────────────────── */}
      {apps.length === 0 ? (
        <div className="sku-card rounded-xl p-10 text-center">
          <AppWindow size={32} className="text-slate-700 mx-auto mb-3" />
          <p className="text-slate-500 text-sm">
            {lang === 'fr'
              ? 'Aucune application enregistrée. Ajoutez votre première application web pour commencer le scan.'
              : 'No application registered. Add your first web app to start scanning.'}
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {apps.map(app => {
            const isExpanded = appExpandedId === app.id;
            const scanResult = appScanResults[app.id];
            const scanDetails = appScanDetails[app.id];
            const verifyMsg  = appVerifyMsg[app.id];
            const showVerifyInfo = appVerifyInfo[app.id];

            return (
              <div key={app.id} className="sku-card rounded-xl overflow-hidden">
                {/* ── Header row ─────────────────────────────── */}
                <div className="flex items-center gap-3 p-4">
                  <SkuIcon color={app.is_verified ? '#4ade80' : '#fbbf24'} size={36}>
                    {app.is_verified
                      ? <CheckCircle2 size={16} className="text-green-300" />
                      : <AlertTriangle size={16} className="text-amber-300" />
                    }
                  </SkuIcon>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="text-white font-semibold text-sm">{app.name}</p>
                      {app.is_verified
                        ? <span className="text-[10px] font-bold text-green-400 bg-green-500/10 border border-green-500/20 px-1.5 py-0.5 rounded">{'\u2713'} V{'\u00C9'}RIFI{'\u00C9'}</span>
                        : <span className="text-[10px] font-bold text-amber-400 bg-amber-500/10 border border-amber-500/20 px-1.5 py-0.5 rounded">EN ATTENTE</span>
                      }
                    </div>
                    <p className="text-slate-500 text-xs font-mono truncate">{app.url}</p>
                  </div>
                  {/* Score badge */}
                  {app.last_score !== null && (
                    <div className={`text-center shrink-0 ${scoreColor(app.last_score)}`}>
                      <p className="text-2xl font-black font-mono">{app.last_score}</p>
                      <p className="text-[10px] text-slate-600">/100</p>
                    </div>
                  )}
                  {/* Actions */}
                  <div className="flex items-center gap-1.5 shrink-0">
                    {/* Vérifier */}
                    {!app.is_verified && (
                      <button
                        title={lang === 'fr' ? 'V\u00E9rifier l\'ownership' : 'Verify ownership'}
                        onClick={() => handleVerifyApp(app.id)}
                        disabled={appVerifyLoading === app.id}
                        className="p-2 rounded-lg text-amber-400 hover:bg-amber-500/10 border border-transparent hover:border-amber-500/20 transition disabled:opacity-40"
                      >
                        {appVerifyLoading === app.id
                          ? <div className="w-3.5 h-3.5 border-2 border-amber-400/30 border-t-amber-400 rounded-full animate-spin" />
                          : <CheckCircle2 size={14} />
                        }
                      </button>
                    )}
                    {/* Info vérification */}
                    {!app.is_verified && (
                      <button
                        title={lang === 'fr' ? 'Instructions de v\u00E9rification' : 'Verification instructions'}
                        onClick={() => setAppVerifyInfo(prev => ({ ...prev, [app.id]: !prev[app.id] }))}
                        className="p-2 rounded-lg text-slate-400 hover:bg-slate-700 border border-transparent hover:border-slate-600 transition"
                      >
                        <FileText size={14} />
                      </button>
                    )}
                    {/* Lancer scan */}
                    {app.is_verified && (
                      <button
                        title={lang === 'fr' ? 'Lancer un scan' : 'Run scan'}
                        onClick={() => handleScanApp(app.id)}
                        disabled={appScanLoading === app.id}
                        className="p-2 rounded-lg text-violet-400 hover:bg-violet-500/10 border border-transparent hover:border-violet-500/20 transition disabled:opacity-40"
                      >
                        {appScanLoading === app.id
                          ? <div className="w-3.5 h-3.5 border-2 border-violet-400/30 border-t-violet-400 rounded-full animate-spin" />
                          : <ScanSearch size={14} />
                        }
                      </button>
                    )}
                    {/* Toggle findings */}
                    {scanResult && (
                      <button
                        onClick={() => setAppExpandedId(isExpanded ? null : app.id)}
                        className="p-2 rounded-lg text-slate-400 hover:bg-slate-700 border border-transparent hover:border-slate-600 transition"
                      >
                        {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                      </button>
                    )}
                    {/* Supprimer */}
                    <button
                      title={lang === 'fr' ? 'Supprimer' : 'Delete'}
                      onClick={() => handleDeleteApp(app.id)}
                      className="p-2 rounded-lg text-slate-600 hover:bg-red-500/10 hover:text-red-400 border border-transparent hover:border-red-500/20 transition"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>

                {/* ── Instructions de vérification ────────────── */}
                {showVerifyInfo && (
                  <div className="mx-4 mb-4 p-4 rounded-xl border border-amber-500/20 bg-amber-500/5">
                    <p className="text-amber-300 text-xs font-semibold mb-2 flex items-center gap-1.5">
                      <FileText size={12} />
                      {lang === 'fr'
                        ? `V\u00E9rification par ${app.verification_method === 'dns' ? 'DNS TXT' : 'fichier .well-known'}`
                        : `Verify via ${app.verification_method === 'dns' ? 'DNS TXT' : '.well-known file'}`}
                    </p>
                    {app.verification_method === 'dns' ? (
                      <div className="flex flex-col gap-1.5 text-xs font-mono">
                        <p className="text-slate-400">{lang === 'fr' ? 'Ajoutez cet enregistrement DNS :' : 'Add this DNS record:'}</p>
                        <div className="bg-slate-900 rounded-lg p-3 flex flex-col gap-1">
                          <span><span className="text-slate-600">Type :</span> <span className="text-cyan-300">TXT</span></span>
                          <span><span className="text-slate-600">Nom  :</span> <span className="text-cyan-300">_cyberhealth-verify.{app.domain}</span></span>
                          <span><span className="text-slate-600">Valeur :</span> <span className="text-green-300">cyberhealth-verify={app.verification_token}</span></span>
                        </div>
                      </div>
                    ) : (
                      <div className="flex flex-col gap-1.5 text-xs font-mono">
                        <p className="text-slate-400">{lang === 'fr' ? 'Cr\u00E9ez ce fichier sur votre serveur :' : 'Create this file on your server:'}</p>
                        <div className="bg-slate-900 rounded-lg p-3 flex flex-col gap-1">
                          <span><span className="text-slate-600">Chemin :</span> <span className="text-cyan-300">/.well-known/cyberhealth-verify.txt</span></span>
                          <span><span className="text-slate-600">Contenu :</span> <span className="text-green-300">cyberhealth-verify={app.verification_token}</span></span>
                        </div>
                      </div>
                    )}
                    {verifyMsg && (
                      <p className={`mt-2 text-xs font-medium ${verifyMsg.ok ? 'text-green-400' : 'text-red-400'}`}>
                        {verifyMsg.ok ? '\u2713 ' : '\u2717 '}{verifyMsg.msg}
                      </p>
                    )}
                  </div>
                )}

                {/* ── Verify message (even without expanded info) ── */}
                {verifyMsg && !showVerifyInfo && (
                  <div className="mx-4 mb-4">
                    <p className={`text-xs font-medium ${verifyMsg.ok ? 'text-green-400' : 'text-amber-400'}`}>
                      {verifyMsg.ok ? '\u2713 ' : '\u26A0 '}{verifyMsg.msg}
                    </p>
                  </div>
                )}

                {/* ── Findings ─────────────────────────────────── */}
                {isExpanded && scanResult && (() => {
                  const sevColors: Record<string, string> = {
                    CRITICAL: 'border-l-red-500 bg-red-500/5',
                    HIGH:     'border-l-orange-500 bg-orange-500/5',
                    MEDIUM:   'border-l-yellow-500 bg-yellow-500/5',
                    LOW:      'border-l-blue-500 bg-blue-500/5',
                    INFO:     'border-l-slate-500 bg-slate-800/30',
                  };
                  const sevText: Record<string, string> = {
                    CRITICAL: 'text-red-400', HIGH: 'text-orange-400',
                    MEDIUM: 'text-yellow-400', LOW: 'text-blue-400', INFO: 'text-slate-400',
                  };
                  // Séparer findings App Scan / Secrets / DAST
                  const appFindings     = scanResult.filter(f => !f.category?.startsWith('DAST') && f.category !== 'Secrets expos\u00E9s');
                  const dastFindings    = scanResult.filter(f => f.category?.startsWith('DAST'));
                  const secretFindings  = scanResult.filter(f => f.category === 'Secrets expos\u00E9s');
                  const dast    = scanDetails?.dast;
                  const secrets = scanDetails?.secrets;
                  return (
                    <div className="border-t border-slate-800 px-4 py-4 flex flex-col gap-4">

                      {/* App Scan findings */}
                      <div className="flex flex-col gap-2">
                        <p className="text-slate-500 text-xs font-mono uppercase tracking-wider">
                          {lang === 'fr' ? 'Scan applicatif passif' : 'Passive app scan'}
                          {' \u2014 '}
                          {appFindings.length === 0
                            ? (lang === 'fr' ? 'aucune vuln\u00E9rabilit\u00E9' : 'no vulnerability')
                            : `${appFindings.length} finding${appFindings.length > 1 ? 's' : ''}`
                          }
                        </p>
                        {appFindings.map((f, i) => (
                          <div key={i} className={`border-l-2 rounded-r-lg p-3 ${sevColors[f.severity] ?? sevColors.INFO}`}>
                            <div className="flex items-start justify-between gap-2">
                              <p className="text-white text-sm font-semibold leading-snug">{f.title}</p>
                              <span className={`text-xs font-bold font-mono shrink-0 ${sevText[f.severity] ?? sevText.INFO}`}>
                                {f.severity}
                                {(f.penalty ?? 0) > 0 && <span className="text-slate-500 font-normal ml-1">{'\u2212'}{f.penalty}pt</span>}
                              </span>
                            </div>
                            {f.plain_explanation && (
                              <p className="text-slate-400 text-xs mt-1 leading-relaxed">{f.plain_explanation}</p>
                            )}
                            {f.recommendation && (
                              <p className="text-cyan-400/70 text-xs mt-1.5 font-mono">{f.recommendation}</p>
                            )}
                          </div>
                        ))}
                      </div>

                      {/* DAST section */}
                      <div className="flex flex-col gap-2">
                        <div className="flex items-center gap-2">
                          <p className="text-violet-400 text-xs font-mono uppercase tracking-wider">
                            DAST {'\u2014'} {lang === 'fr' ? 'Tests actifs sur formulaires' : 'Active form tests'}
                          </p>
                          {dast && (
                            <span className="text-[10px] font-mono text-slate-600">
                              {lang === 'fr'
                                ? `${dast.forms_found} form${dast.forms_found > 1 ? 's' : ''} trouv\u00E9${dast.forms_found > 1 ? 's' : ''}, ${dast.forms_tested} test\u00E9${dast.forms_tested > 1 ? 's' : ''}`
                                : `${dast.forms_found} form${dast.forms_found !== 1 ? 's' : ''} found, ${dast.forms_tested} tested`
                              }
                            </span>
                          )}
                        </div>

                        {/* Error / no forms */}
                        {dast?.error && (
                          <p className="text-amber-400/70 text-xs font-mono">{dast.error}</p>
                        )}
                        {dast && !dast.error && dast.forms_found === 0 && (
                          <p className="text-slate-600 text-xs italic">
                            {lang === 'fr' ? 'Aucun formulaire HTML d\u00E9couvert.' : 'No HTML form discovered.'}
                          </p>
                        )}
                        {dast && !dast.error && dast.forms_found > 0 && dastFindings.length === 0 && (
                          <p className="text-green-400/70 text-xs flex items-center gap-1">
                            <Check size={11} />
                            {lang === 'fr' ? 'Aucune vuln\u00E9rabilit\u00E9 d\u00E9tect\u00E9e (XSS, SQLi, CSRF)' : 'No vulnerability detected (XSS, SQLi, CSRF)'}
                          </p>
                        )}

                        {/* DAST findings avec evidence */}
                        {dast?.findings?.filter(df => df.severity !== 'INFO').map((df, i) => (
                          <div key={i} className={`border-l-2 rounded-r-lg p-3 ${sevColors[df.severity] ?? sevColors.INFO}`}>
                            <div className="flex items-start justify-between gap-2 mb-1">
                              <p className="text-white text-sm font-semibold leading-snug">{df.title}</p>
                              <div className="flex items-center gap-1.5 shrink-0">
                                <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded border ${
                                  df.test_type === 'xss'  ? 'text-orange-300 border-orange-500/30 bg-orange-500/10' :
                                  df.test_type === 'sqli' ? 'text-red-300 border-red-500/30 bg-red-500/10' :
                                  'text-yellow-300 border-yellow-500/30 bg-yellow-500/10'
                                }`}>
                                  {df.test_type.toUpperCase()}
                                </span>
                                <span className={`text-xs font-bold font-mono ${sevText[df.severity] ?? sevText.INFO}`}>
                                  {df.severity}
                                  {df.penalty > 0 && <span className="text-slate-500 font-normal ml-1">{'\u2212'}{df.penalty}pt</span>}
                                </span>
                              </div>
                            </div>
                            {/* Champ + URL action */}
                            {(df.field_name || df.form_action) && (
                              <div className="flex items-center gap-3 text-[10px] font-mono text-slate-500 mb-1.5">
                                {df.field_name && (
                                  <span>
                                    <span className="text-slate-600">{lang === 'fr' ? 'Champ :' : 'Field:'} </span>
                                    <span className="text-cyan-400/70">{df.field_name}</span>
                                  </span>
                                )}
                                {df.form_action && (
                                  <span className="truncate max-w-[200px]">
                                    <span className="text-slate-600">{lang === 'fr' ? 'Action :' : 'Action:'} </span>
                                    <span className="text-slate-400">{df.form_action}</span>
                                  </span>
                                )}
                              </div>
                            )}
                            {/* Evidence */}
                            {df.evidence && (
                              <div className="bg-slate-900 rounded px-2.5 py-1.5 font-mono text-[10px] text-amber-300/80 break-all mb-1.5">
                                {df.evidence}
                              </div>
                            )}
                            <p className="text-slate-400 text-xs leading-relaxed">{df.detail}</p>
                          </div>
                        ))}
                      </div>

                      {/* Secrets section */}
                      <div className="flex flex-col gap-2">
                        <div className="flex items-center gap-2">
                          <p className="text-red-400 text-xs font-mono uppercase tracking-wider">
                            {lang === 'fr' ? 'Secrets expos\u00E9s dans le bundle' : 'Secrets exposed in bundle'}
                          </p>
                          {secrets && (
                            <span className="text-[10px] font-mono text-slate-600">
                              {lang === 'fr'
                                ? `${secrets.scripts_found} script${secrets.scripts_found > 1 ? 's' : ''} trouv\u00E9${secrets.scripts_found > 1 ? 's' : ''}, ${secrets.scripts_scanned} analys\u00E9${secrets.scripts_scanned > 1 ? 's' : ''}`
                                : `${secrets.scripts_found} script${secrets.scripts_found !== 1 ? 's' : ''} found, ${secrets.scripts_scanned} scanned`
                              }
                            </span>
                          )}
                        </div>

                        {secrets?.error && (
                          <p className="text-amber-400/70 text-xs font-mono">{secrets.error}</p>
                        )}
                        {secrets && !secrets.error && secrets.scripts_scanned === 0 && secrets.scripts_found === 0 && (
                          <p className="text-slate-600 text-xs italic">
                            {lang === 'fr' ? 'Aucun bundle JS externe d\u00E9couvert.' : 'No external JS bundle discovered.'}
                          </p>
                        )}
                        {secrets && !secrets.error && secrets.scripts_scanned > 0 && secretFindings.length === 0 && (
                          <p className="text-green-400/70 text-xs flex items-center gap-1">
                            <Check size={11} />
                            {lang === 'fr' ? 'Aucun secret d\u00E9tect\u00E9 dans les bundles analys\u00E9s' : 'No secret detected in scanned bundles'}
                          </p>
                        )}

                        {/* Secret findings */}
                        {secrets?.findings?.map((sf, i) => (
                          <div key={i} className={`border-l-2 rounded-r-lg p-3 ${sevColors[sf.severity] ?? sevColors.INFO}`}>
                            <div className="flex items-start justify-between gap-2 mb-1">
                              <p className="text-white text-sm font-semibold leading-snug">{sf.pattern_name}</p>
                              <span className={`text-xs font-bold font-mono shrink-0 ${sevText[sf.severity] ?? sevText.INFO}`}>
                                {sf.severity}
                                {sf.penalty > 0 && <span className="text-slate-500 font-normal ml-1">{'\u2212'}{sf.penalty}pt</span>}
                              </span>
                            </div>

                            {/* Valeur masquée + source */}
                            <div className="flex items-center gap-3 text-[10px] font-mono text-slate-500 mb-1.5 flex-wrap">
                              <span>
                                <span className="text-slate-600">{lang === 'fr' ? 'Valeur :' : 'Value:'} </span>
                                <span className="text-red-300/80">{sf.matched_value}</span>
                              </span>
                              {sf.source_url && (
                                <span className="truncate max-w-[240px]">
                                  <span className="text-slate-600">{lang === 'fr' ? 'Source :' : 'Source:'} </span>
                                  <span className="text-slate-400">{sf.source_url.replace(/^https?:\/\/[^/]+/, '')}</span>
                                </span>
                              )}
                            </div>

                            {/* Contexte (extrait du bundle) */}
                            {sf.context && (
                              <div className="bg-slate-900 rounded px-2.5 py-1.5 font-mono text-[10px] text-slate-400 break-all mb-1.5">
                                {sf.context}
                              </div>
                            )}

                            <p className="text-slate-400 text-xs leading-relaxed mb-1.5">{sf.description}</p>
                            <p className="text-cyan-400/70 text-[10px] font-mono leading-relaxed">{sf.recommendation}</p>
                          </div>
                        ))}
                      </div>

                    </div>
                  );
                })()}
              </div>
            );
          })}
        </div>
      )}

    </div>
  );
}
