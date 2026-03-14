import { Globe, AlertTriangle, Plus } from 'lucide-react';
import SkuIcon from '../SkuIcon';
import type { MonitoredDomain, ScanHistoryItem, Tab } from './types';
import { scoreColor, scoreBorder, RiskBadge, Sparkline } from './helpers';

interface Props {
  domains: MonitoredDomain[];
  planLimit: number | null;
  avgScore: number | null;
  criticalDomains: number;
  totalOpenFindings: number;
  historyByDomain: Record<string, ScanHistoryItem[]>;
  setTab: (tab: Tab) => void;
  lang: 'fr' | 'en';
}

export default function OverviewTab({
  domains,
  planLimit,
  avgScore,
  criticalDomains,
  totalOpenFindings,
  historyByDomain,
  setTab,
  lang,
}: Props) {
  return (
    <div className="flex flex-col gap-6">

      {/* KPI cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">

        {/* Domaines surveilles */}
        <div className="sku-card rounded-xl p-4">
          <p className="text-slate-500 text-xs font-mono uppercase tracking-wider mb-2">{lang === 'fr' ? 'Domaines surveilles' : 'Monitored domains'}</p>
          <p className="text-3xl font-black font-mono text-white">
            {domains.length}
            <span className="text-slate-600 text-base">
              /{planLimit !== null ? planLimit : '\u221E'}
            </span>
          </p>
          <div className="mt-3 h-1 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.06)' }}>
            <div
              className="h-1 bg-cyan-500 rounded-full transition-all"
              style={{ width: planLimit !== null ? `${Math.min((domains.length / planLimit) * 100, 100)}%` : '100%' }}
            />
          </div>
        </div>

        {/* Score moyen */}
        <div className="sku-card rounded-xl p-4" style={avgScore !== null ? {
          borderColor: avgScore >= 70 ? 'rgba(52,211,153,0.2)' : avgScore >= 40 ? 'rgba(251,191,36,0.2)' : 'rgba(248,113,113,0.2)',
        } : {}}>
          <p className="text-slate-500 text-xs font-mono uppercase tracking-wider mb-2">{lang === 'fr' ? 'Score moyen' : 'Average score'}</p>
          <p className={`text-3xl font-black font-mono ${scoreColor(avgScore)}`}>
            {avgScore !== null ? avgScore : '\u2014'}
            {avgScore !== null && <span className="text-base opacity-60">/100</span>}
          </p>
        </div>

        {/* Domaines critiques */}
        <div className="sku-card rounded-xl p-4" style={criticalDomains > 0 ? {
          borderColor: 'rgba(248,113,113,0.25)',
          background: 'linear-gradient(180deg,rgba(30,10,10,0.9) 0%,rgba(20,5,5,0.95) 100%)',
        } : {}}>
          <p className="text-slate-500 text-xs font-mono uppercase tracking-wider mb-2">{lang === 'fr' ? 'Domaines critiques' : 'Critical domains'}</p>
          <div className="flex items-end gap-2">
            <p className={`text-3xl font-black font-mono ${criticalDomains > 0 ? 'text-red-400' : 'text-slate-500'}`}>
              {criticalDomains}
            </p>
            {criticalDomains > 0 && <AlertTriangle size={16} className="text-red-400 mb-1" />}
          </div>
        </div>

        {/* Findings ouverts */}
        <div className="sku-card rounded-xl p-4" style={totalOpenFindings > 0 ? {
          borderColor: 'rgba(251,191,36,0.2)',
        } : {}}>
          <p className="text-slate-500 text-xs font-mono uppercase tracking-wider mb-2">{lang === 'fr' ? 'Findings ouverts' : 'Open findings'}</p>
          <p className={`text-3xl font-black font-mono ${totalOpenFindings > 0 ? 'text-amber-400' : 'text-slate-500'}`}>
            {totalOpenFindings}
          </p>
          <p className="text-slate-600 text-xs font-mono mt-1">
            {lang === 'fr' ? 'tous domaines' : 'all domains'}
          </p>
        </div>
      </div>

      {/* Domain cards */}
      {domains.length === 0 ? (
        <div className="flex flex-col items-center gap-4 py-20 text-center">
          <SkuIcon color="#22d3ee" size={52}><Globe size={24} className="text-cyan-300" /></SkuIcon>
          <p className="text-slate-300 font-bold text-lg">{lang === 'fr' ? 'Aucun domaine sous surveillance' : 'No domain monitored'}</p>
          <p className="text-slate-600 text-sm max-w-sm">
            {lang === 'fr' ? 'Activez le monitoring pour recevoir des alertes automatiques chaque semaine.' : 'Enable monitoring to receive automatic alerts every week.'}
          </p>
          <button
            onClick={() => setTab('monitoring')}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 hover:bg-cyan-500/30 transition text-sm font-semibold"
          >
            <Plus size={14} /> {lang === 'fr' ? 'Ajouter un domaine' : 'Add a domain'}
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {domains.map(d => {
            const domainScans = [...(historyByDomain[d.domain] ?? [])].reverse();
            const scores = domainScans.map(h => h.security_score);
            const scanCount = historyByDomain[d.domain]?.length ?? 0;

            return (
              <div key={d.domain} className={`rounded-xl border p-5 flex flex-col gap-3 ${scoreBorder(d.last_score)}`}>
                {/* Domain + risk */}
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <Globe size={13} className="text-slate-500 shrink-0 mt-0.5" />
                    <span className="text-white font-mono text-sm font-bold truncate">{d.domain}</span>
                  </div>
                  <RiskBadge level={d.last_risk_level} />
                </div>

                {/* Score + sparkline */}
                <div className="flex items-end justify-between">
                  <div>
                    <p className={`text-4xl font-black font-mono leading-none ${scoreColor(d.last_score)}`}>
                      {d.last_score ?? '\u2014'}
                    </p>
                    <p className="text-slate-600 text-xs font-mono mt-0.5">/100</p>
                  </div>
                  <Sparkline scores={scores} width={90} height={36} />
                </div>

                {/* Footer */}
                <div className="flex items-center justify-between text-[10px] font-mono text-slate-600 border-t border-slate-800/80 pt-2">
                  <span>
                    {d.last_scan_at
                      ? `${lang === 'fr' ? 'Dernier scan' : 'Last scan'} ${new Date(d.last_scan_at).toLocaleDateString(lang === 'fr' ? 'fr-FR' : 'en-GB')}`
                      : lang === 'fr' ? 'Aucun scan' : 'No scan'}
                  </span>
                  <span>{scanCount} scan{scanCount !== 1 ? 's' : ''}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
