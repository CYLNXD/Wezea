import { X, Shield, FileDown, ExternalLink, Check } from 'lucide-react';
import type { MonitoredDomain, ScanHistoryItem } from './types';
import { scoreColor, RiskBadge, Sparkline, ScoreLineChart } from './helpers';

interface Props {
  domains: MonitoredDomain[];
  history: ScanHistoryItem[];
  filteredHistory: ScanHistoryItem[];
  historyByDomain: Record<string, ScanHistoryItem[]>;
  historyDomain: string;
  setHistoryDomain: (d: string) => void;
  isPremium: boolean;
  pdfLoading: string | null;
  exportLoading: string | null;
  shareLoading: string | null;
  shareCopied: string | null;
  scanModalLoading: string | null;
  generatePdf: (uuid: string, domain: string) => void;
  exportScan: (uuid: string, domain: string, format: 'json' | 'csv') => void;
  toggleShare: (uuid: string) => void;
  openScanModal: (uuid: string) => void;
  lang: 'fr' | 'en';
}

export default function HistoryTab({
  history,
  filteredHistory,
  historyByDomain,
  historyDomain,
  setHistoryDomain,
  isPremium,
  pdfLoading,
  exportLoading,
  shareLoading,
  shareCopied,
  scanModalLoading,
  generatePdf,
  exportScan,
  toggleShare,
  openScanModal,
  lang,
}: Props) {
  return (
    <div className="flex flex-col gap-5">

      {/* Domain sparkline cards */}
      {Object.keys(historyByDomain).length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {Object.entries(historyByDomain).map(([domain, scans]) => {
            const sorted = [...scans].sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
            const scores = sorted.map(s => s.security_score);
            const latest = scans[0];
            const isActive = historyDomain === domain;

            return (
              <button
                key={domain}
                onClick={() => setHistoryDomain(isActive ? 'all' : domain)}
                className={`
                  rounded-xl border p-4 text-left transition-all
                  ${isActive
                    ? 'border-cyan-500/40 bg-cyan-500/5 ring-1 ring-cyan-500/20'
                    : 'border-slate-800 bg-slate-900 hover:border-slate-700'}
                `}
              >
                <div className="flex items-center justify-between mb-3">
                  <span className="text-white font-mono text-sm font-bold truncate max-w-[130px]">{domain}</span>
                  <span className={`text-xl font-black font-mono ${scoreColor(latest?.security_score ?? null)}`}>
                    {latest?.security_score ?? '\u2014'}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-600 text-xs font-mono">{scans.length} scan{scans.length !== 1 ? 's' : ''}</span>
                  <Sparkline scores={scores} width={90} height={28} />
                </div>
              </button>
            );
          })}
        </div>
      )}

      {/* Full chart for selected domain */}
      {historyDomain !== 'all' && historyByDomain[historyDomain] && (
        <div className="flex flex-col gap-2">
          <p className="text-sm font-bold text-white">
            {lang === 'fr' ? '\u00C9volution du score' : 'Score evolution'} — <span className="text-cyan-400 font-mono">{historyDomain}</span>
          </p>
          <ScoreLineChart scans={historyByDomain[historyDomain]} lang={lang} />
        </div>
      )}

      {/* All domains filter pill */}
      {historyDomain !== 'all' && (
        <button
          onClick={() => setHistoryDomain('all')}
          className="self-start flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300 transition font-mono border border-slate-800 rounded-lg px-3 py-1.5 hover:border-slate-700"
        >
          <X size={11} />
          {lang === 'fr' ? 'Voir tous les domaines' : 'View all domains'}
        </button>
      )}

      {/* Scan list table */}
      {filteredHistory.length === 0 ? (
        <div className="py-16 text-center text-slate-600 text-sm">
          {history.length === 0 ? (lang === 'fr' ? 'Aucun scan dans votre historique.' : 'No scan in your history.') : (lang === 'fr' ? 'Aucun scan pour ce domaine.' : 'No scan for this domain.')}
        </div>
      ) : (
        <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
          <div className="px-5 py-3 border-b border-slate-800 flex items-center justify-between">
            <p className="text-white font-bold text-sm">
              {filteredHistory.length} scan{filteredHistory.length !== 1 ? 's' : ''}
              {historyDomain !== 'all' && <span className="text-cyan-400 font-mono ml-2">{historyDomain}</span>}
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-800">
                  <th className="px-5 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">{lang === 'fr' ? 'Domaine' : 'Domain'}</th>
                  <th className="px-4 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">Score</th>
                  <th className="px-4 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">{lang === 'fr' ? 'Risque' : 'Risk'}</th>
                  <th className="px-4 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">Findings</th>
                  <th className="px-4 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">{lang === 'fr' ? 'Date' : 'Date'}</th>
                  <th className="px-4 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">{lang === 'fr' ? 'Dur\u00E9e' : 'Duration'}</th>
                  {isPremium ? (
                    <>
                      <th className="px-4 py-3 text-xs font-mono text-slate-500 uppercase tracking-wider">{lang === 'fr' ? 'Voir' : 'View'}</th>
                      <th className="px-4 py-3 text-xs font-mono text-slate-500 uppercase tracking-wider">PDF</th>
                      <th className="px-4 py-3 text-xs font-mono text-slate-500 uppercase tracking-wider">Export</th>
                      <th className="px-4 py-3 text-xs font-mono text-slate-500 uppercase tracking-wider">{lang === 'fr' ? 'Lien' : 'Share'}</th>
                    </>
                  ) : null}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/40">
                {filteredHistory.map(scan => (
                  <tr key={scan.scan_uuid} className="hover:bg-slate-800/25 transition-colors">
                    <td className="px-5 py-3.5 font-mono text-slate-300 text-xs">{scan.domain}</td>
                    <td className="px-4 py-3.5">
                      <span className={`text-lg font-black font-mono ${scoreColor(scan.security_score)}`}>
                        {scan.security_score}
                      </span>
                    </td>
                    <td className="px-4 py-3.5"><RiskBadge level={scan.risk_level} /></td>
                    <td className="px-4 py-3.5 text-slate-500 font-mono text-xs">{scan.findings_count}</td>
                    <td className="px-4 py-3.5 text-slate-500 text-xs font-mono">
                      {new Date(scan.created_at).toLocaleDateString(lang === 'fr' ? 'fr-FR' : 'en-GB', {
                        day: '2-digit', month: '2-digit', year: 'numeric',
                        hour: '2-digit', minute: '2-digit',
                      })}
                    </td>
                    <td className="px-4 py-3.5 text-slate-600 text-xs font-mono">{scan.scan_duration}s</td>
                    {isPremium && (
                      <>
                        <td className="px-4 py-3.5">
                          <button
                            onClick={() => openScanModal(scan.scan_uuid)}
                            disabled={scanModalLoading === scan.scan_uuid}
                            title={lang === 'fr' ? 'Voir les r\u00E9sultats' : 'View results'}
                            className="flex items-center gap-1 text-xs text-cyan-400 hover:text-cyan-200 transition disabled:opacity-40"
                          >
                            {scanModalLoading === scan.scan_uuid
                              ? <div className="w-3 h-3 border-2 border-cyan-400/30 border-t-cyan-400 rounded-full animate-spin" />
                              : <Shield size={13} />
                            }
                            {lang === 'fr' ? 'Voir' : 'View'}
                          </button>
                        </td>
                        <td className="px-4 py-3.5">
                          <button
                            onClick={() => generatePdf(scan.scan_uuid, scan.domain)}
                            disabled={pdfLoading === scan.scan_uuid}
                            className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-200 transition disabled:opacity-40"
                          >
                            {pdfLoading === scan.scan_uuid
                              ? <div className="w-3 h-3 border-2 border-cyan-400/30 border-t-cyan-400 rounded-full animate-spin" />
                              : <FileDown size={13} />
                            }
                            PDF
                          </button>
                        </td>
                        <td className="px-4 py-3.5">
                          <div className="flex items-center gap-2">
                            <button
                              onClick={() => exportScan(scan.scan_uuid, scan.domain, 'json')}
                              disabled={exportLoading === `${scan.scan_uuid}-json`}
                              title={lang === 'fr' ? 'T\u00E9l\u00E9charger JSON' : 'Download JSON'}
                              className="text-xs font-mono text-slate-400 hover:text-cyan-400 transition disabled:opacity-40"
                            >
                              {exportLoading === `${scan.scan_uuid}-json`
                                ? <div className="w-3 h-3 border-2 border-cyan-400/30 border-t-cyan-400 rounded-full animate-spin" />
                                : 'JSON'}
                            </button>
                            <span className="text-slate-700">|</span>
                            <button
                              onClick={() => exportScan(scan.scan_uuid, scan.domain, 'csv')}
                              disabled={exportLoading === `${scan.scan_uuid}-csv`}
                              title={lang === 'fr' ? 'T\u00E9l\u00E9charger CSV' : 'Download CSV'}
                              className="text-xs font-mono text-slate-400 hover:text-emerald-400 transition disabled:opacity-40"
                            >
                              {exportLoading === `${scan.scan_uuid}-csv`
                                ? <div className="w-3 h-3 border-2 border-emerald-400/30 border-t-emerald-400 rounded-full animate-spin" />
                                : 'CSV'}
                            </button>
                          </div>
                        </td>
                        <td className="px-4 py-3.5">
                          <button
                            onClick={() => toggleShare(scan.scan_uuid)}
                            disabled={shareLoading === scan.scan_uuid}
                            title={
                              shareCopied === scan.scan_uuid
                                ? (lang === 'fr' ? 'Lien copi\u00E9 !' : 'Link copied!')
                                : scan.public_share
                                  ? (lang === 'fr' ? 'D\u00E9sactiver le lien public' : 'Disable public link')
                                  : (lang === 'fr' ? 'Activer le lien public' : 'Enable public link')
                            }
                            className={`flex items-center gap-1 text-xs transition disabled:opacity-40 ${
                              shareCopied === scan.scan_uuid
                                ? 'text-green-400'
                                : scan.public_share
                                  ? 'text-violet-400 hover:text-violet-300'
                                  : 'text-slate-500 hover:text-slate-300'
                            }`}
                          >
                            {shareLoading === scan.scan_uuid
                              ? <div className="w-3 h-3 border-2 border-slate-400/30 border-t-slate-400 rounded-full animate-spin" />
                              : shareCopied === scan.scan_uuid
                                ? <Check size={13} />
                                : <ExternalLink size={13} />
                            }
                            {shareCopied === scan.scan_uuid
                              ? (lang === 'fr' ? 'Copi\u00E9' : 'Copied')
                              : scan.public_share
                                ? (lang === 'fr' ? 'Actif' : 'Active')
                                : (lang === 'fr' ? 'Partager' : 'Share')}
                          </button>
                        </td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
