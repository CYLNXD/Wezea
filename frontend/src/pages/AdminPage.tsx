// ─── AdminPage.tsx — Dashboard admin Wezea ─────────────────────────────────
import { useState, useEffect, useMemo } from 'react';
import { motion } from 'framer-motion';
import {
  Shield, Users, Trash2, RefreshCw, CheckCircle, XCircle,
  TrendingUp, DollarSign, UserPlus, ArrowUpRight, Zap, BarChart3,
  BookOpen, Plus, Pencil, X, ExternalLink, Activity,
} from 'lucide-react';
import { apiClient } from '../lib/api';
import { useAuth } from '../contexts/AuthContext';
import PageNavbar from '../components/PageNavbar';
import SkuIcon from '../components/SkuIcon';

// ─── Types ────────────────────────────────────────────────────────────────────

interface UserAdmin {
  id: number;
  email: string;
  plan: string;
  is_active: boolean;
  is_admin: boolean;
  scan_count: number;
  created_at: string;
  mfa_enabled?: boolean;
}

interface Metrics {
  mrr_cents: number;
  plan_breakdown: Record<string, number>;
  revenue_30d_cents: number;
  conversions_30d: number;
  churns_30d: number;
  new_signups_30d: number;
  active_users_7d: number;
  conversion_rate: number;
  signups_last_30d: { date: string; count: number }[];
  scans_last_14d: { date: string; count: number }[];
}

interface Stats {
  total_users: number;
  active_users: number;
  pro_users: number;
  free_users: number;
  total_scans: number;
}

interface BlogLink {
  id: number;
  match_keyword: string;
  article_title: string;
  article_url: string;
}

interface Props {
  onBack?: () => void;
  onGoHistory?: () => void;
  onGoClientSpace?: () => void;
  onGoContact?: () => void;
}

type Tab = 'metrics' | 'performance' | 'users' | 'blog';

// ─── Types Performance ─────────────────────────────────────────────────────────

interface PerfEndpoint {
  method:    string;
  path:      string;
  count:     number;
  avg_ms:    number;
  p50_ms:    number;
  p95_ms:    number;
  p99_ms:    number;
  max_ms:    number;
  error_5xx: number;
  slow_pct:  number;
}

interface SlowRequest {
  method:      string;
  path:        string;
  status_code: number;
  duration_ms: number;
  ts:          string;
}

interface PerfStats {
  total_requests:    number;
  buffer_size:       number;
  slow_threshold_ms: number;
  endpoints:         PerfEndpoint[];
  slow_requests:     SlowRequest[];
}

// ─── Plan config ──────────────────────────────────────────────────────────────

const PLAN_COLORS: Record<string, string> = {
  free:    'text-slate-400 bg-slate-800 border-slate-700',
  starter: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30',
  pro:     'text-cyan-400 bg-cyan-500/10 border-cyan-500/30',
  dev:     'text-violet-400 bg-violet-500/10 border-violet-500/30',
  team:    'text-purple-400 bg-purple-500/10 border-purple-500/30',
};

const PLAN_BAR_COLORS: Record<string, string> = {
  free:    'bg-slate-600',
  starter: 'bg-emerald-500',
  pro:     'bg-cyan-500',
  dev:     'bg-violet-500',
  team:    'bg-purple-500',
};

// ─── Sparkline SVG ────────────────────────────────────────────────────────────

function Sparkline({
  data,
  color = '#06b6d4',
  width = 160,
  height = 48,
}: {
  data: { date: string; count: number }[];
  color?: string;
  width?: number;
  height?: number;
}) {
  const values = useMemo(() => {
    if (!data.length) return [];
    // Fill all dates in range
    const map = new Map(data.map(d => [d.date, d.count]));
    const sorted = [...data].sort((a, b) => a.date.localeCompare(b.date));
    if (!sorted.length) return [];
    const start = new Date(sorted[0].date);
    const end   = new Date(sorted[sorted.length - 1].date);
    const out: number[] = [];
    for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
      const key = d.toISOString().split('T')[0];
      out.push(map.get(key) ?? 0);
    }
    return out;
  }, [data]);

  if (!values.length || values.every(v => v === 0)) {
    return (
      <div
        style={{ width, height }}
        className="flex items-center justify-center"
      >
        <span className="text-slate-700 text-[10px] font-mono">pas encore de données</span>
      </div>
    );
  }

  const max = Math.max(...values, 1);
  const pad = 4;
  const step = (width - pad * 2) / Math.max(values.length - 1, 1);

  const pts = values.map((v, i) => ({
    x: pad + i * step,
    y: pad + (1 - v / max) * (height - pad * 2),
  }));

  const linePath = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
  const fillPath = `${linePath} L${(pad + (values.length - 1) * step).toFixed(1)},${height} L${pad},${height} Z`;

  const gradId = `sg-${color.replace('#', '')}`;

  return (
    <svg width={width} height={height}>
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stopColor={color} stopOpacity="0.35" />
          <stop offset="100%" stopColor={color} stopOpacity="0.02" />
        </linearGradient>
      </defs>
      <path d={fillPath} fill={`url(#${gradId})`} />
      <path d={linePath} stroke={color} strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      {/* last dot */}
      <circle cx={pts[pts.length - 1].x} cy={pts[pts.length - 1].y} r="2.5" fill={color} />
    </svg>
  );
}

// ─── KPI Card ─────────────────────────────────────────────────────────────────

function KpiCard({
  label,
  value,
  sub,
  color,
  icon: Icon,
  trend,
}: {
  label: string;
  value: string;
  sub?: string;
  color: string;        // hex color, e.g. '#4ade80'
  icon: React.ElementType;
  trend?: 'up' | 'down' | 'neutral';
}) {
  const trendClass = trend === 'up' ? 'text-emerald-400' : trend === 'down' ? 'text-red-400' : 'text-slate-500';
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="sku-card rounded-xl p-4 flex flex-col gap-2"
    >
      <div className="flex items-center justify-between">
        <span className="text-slate-500 text-[11px] font-mono uppercase tracking-wider">{label}</span>
        <SkuIcon color={color} size={28}>
          <Icon size={13} style={{ color }} />
        </SkuIcon>
      </div>
      <p className="text-2xl font-black font-mono text-white">{value}</p>
      {sub && <p className={`text-[11px] font-mono ${trendClass}`}>{sub}</p>}
    </motion.div>
  );
}

// ─── Metrics Tab ──────────────────────────────────────────────────────────────

// ─── PerformanceTab ────────────────────────────────────────────────────────────

function PerformanceTab({ perf, onRefresh }: { perf: PerfStats | null; onRefresh: () => void }) {
  const _msColor = (ms: number) => {
    if (ms < 100)  return 'text-green-400';
    if (ms < 300)  return 'text-yellow-400';
    if (ms < 500)  return 'text-amber-400';
    return 'text-red-400';
  };
  const _methodBadge = (m: string) => {
    const colors: Record<string, string> = {
      GET:    'bg-cyan-500/15 text-cyan-300',
      POST:   'bg-violet-500/15 text-violet-300',
      PATCH:  'bg-amber-500/15 text-amber-300',
      DELETE: 'bg-red-500/15 text-red-300',
    };
    return colors[m] ?? 'bg-slate-500/15 text-slate-300';
  };

  if (!perf) return (
    <div className="flex items-center justify-center py-20 text-slate-500 text-sm">
      Chargement des métriques de performance…
    </div>
  );

  return (
    <div className="flex flex-col gap-5">

      {/* Header + refresh */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center">
            <Activity size={14} className="text-cyan-400" />
          </div>
          <div>
            <p className="text-sm font-semibold text-slate-100">Performance API</p>
            <p className="text-xs text-slate-400">
              {perf.total_requests} requêtes dans le buffer ({perf.buffer_size} max) — seuil lent : {perf.slow_threshold_ms} ms
            </p>
          </div>
        </div>
        <button
          onClick={onRefresh}
          className="sku-btn-ghost px-3 py-1.5 rounded-lg text-xs flex items-center gap-1.5"
        >
          <RefreshCw size={12} /> Rafraîchir
        </button>
      </div>

      {perf.total_requests === 0 ? (
        <div className="sku-card rounded-xl p-8 text-center text-slate-400 text-sm">
          Aucune requête enregistrée. Le buffer se remplit au fil du trafic.
        </div>
      ) : (
        <>
          {/* Tableau endpoints */}
          <div className="sku-card rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-white/5 flex items-center gap-2">
              <BarChart3 size={13} className="text-cyan-400" />
              <span className="text-xs font-semibold text-slate-200">Endpoints (top {perf.endpoints.length})</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-white/5 text-slate-500">
                    <th className="text-left px-4 py-2.5 font-medium">Endpoint</th>
                    <th className="text-right px-3 py-2.5 font-medium">Req</th>
                    <th className="text-right px-3 py-2.5 font-medium">Avg</th>
                    <th className="text-right px-3 py-2.5 font-medium">p50</th>
                    <th className="text-right px-3 py-2.5 font-medium">p95</th>
                    <th className="text-right px-3 py-2.5 font-medium">p99</th>
                    <th className="text-right px-3 py-2.5 font-medium">Max</th>
                    <th className="text-right px-3 py-2.5 font-medium">5xx</th>
                    <th className="text-right px-4 py-2.5 font-medium">Lent%</th>
                  </tr>
                </thead>
                <tbody>
                  {perf.endpoints.map((ep, i) => (
                    <tr key={i} className="border-b border-white/5 last:border-0 hover:bg-white/2">
                      <td className="px-4 py-2.5">
                        <div className="flex items-center gap-2">
                          <span className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold ${_methodBadge(ep.method)}`}>
                            {ep.method}
                          </span>
                          <span className="text-slate-200 font-mono truncate max-w-[220px]" title={ep.path}>
                            {ep.path}
                          </span>
                        </div>
                      </td>
                      <td className="px-3 py-2.5 text-right text-slate-300 font-mono">{ep.count}</td>
                      <td className={`px-3 py-2.5 text-right font-mono font-semibold ${_msColor(ep.avg_ms)}`}>{ep.avg_ms}ms</td>
                      <td className={`px-3 py-2.5 text-right font-mono ${_msColor(ep.p50_ms)}`}>{ep.p50_ms}ms</td>
                      <td className={`px-3 py-2.5 text-right font-mono ${_msColor(ep.p95_ms)}`}>{ep.p95_ms}ms</td>
                      <td className={`px-3 py-2.5 text-right font-mono ${_msColor(ep.p99_ms)}`}>{ep.p99_ms}ms</td>
                      <td className={`px-3 py-2.5 text-right font-mono ${_msColor(ep.max_ms)}`}>{ep.max_ms}ms</td>
                      <td className={`px-3 py-2.5 text-right font-mono ${ep.error_5xx > 0 ? 'text-red-400 font-bold' : 'text-slate-500'}`}>
                        {ep.error_5xx}
                      </td>
                      <td className={`px-4 py-2.5 text-right font-mono ${ep.slow_pct > 10 ? 'text-amber-400' : 'text-slate-500'}`}>
                        {ep.slow_pct}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Top 5 requêtes les plus lentes */}
          {perf.slow_requests.length > 0 && (
            <div className="sku-card rounded-xl overflow-hidden">
              <div className="px-4 py-3 border-b border-white/5 flex items-center gap-2">
                <Zap size={13} className="text-amber-400" />
                <span className="text-xs font-semibold text-slate-200">Top 5 requêtes les plus lentes</span>
              </div>
              <div className="divide-y divide-white/5">
                {perf.slow_requests.map((r, i) => (
                  <div key={i} className="flex items-center gap-3 px-4 py-2.5 hover:bg-white/2">
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold ${_methodBadge(r.method)}`}>
                      {r.method}
                    </span>
                    <span className="text-slate-200 font-mono text-xs flex-1 truncate">{r.path}</span>
                    <span className={`text-xs font-mono font-bold ${r.status_code >= 500 ? 'text-red-400' : 'text-slate-400'}`}>
                      {r.status_code}
                    </span>
                    <span className="text-red-400 font-mono text-xs font-bold">{r.duration_ms}ms</span>
                    <span className="text-slate-500 text-[10px]">
                      {new Date(r.ts).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}


function MetricsTab({ metrics, stats }: { metrics: Metrics | null; stats: Stats | null }) {
  if (!metrics || !stats) {
    return (
      <div className="flex items-center justify-center py-24">
        <div className="w-6 h-6 border-2 border-cyan-500/30 border-t-cyan-500 rounded-full animate-spin" />
      </div>
    );
  }

  const mrr    = (metrics.mrr_cents / 100).toFixed(2);
  const rev30d = (metrics.revenue_30d_cents / 100).toFixed(2);
  const totalPlanUsers = Object.values(metrics.plan_breakdown).reduce((a, b) => a + b, 0) || 1;

  const kpis = [
    {
      label: 'MRR',
      value: `${mrr} €`,
      sub: `revenu mensuel récurrent`,
      color: '#4ade80',   // emerald
      icon: DollarSign,
      trend: 'neutral' as const,
    },
    {
      label: 'Revenu 30j',
      value: `${rev30d} €`,
      sub: `${metrics.conversions_30d} paiement${metrics.conversions_30d > 1 ? 's' : ''} complété${metrics.conversions_30d > 1 ? 's' : ''}`,
      color: '#22d3ee',   // cyan
      icon: TrendingUp,
      trend: metrics.conversions_30d > 0 ? 'up' as const : 'neutral' as const,
    },
    {
      label: 'Taux de conversion',
      value: `${metrics.conversion_rate}%`,
      sub: `free → payant (total)`,
      color: '#a78bfa',   // violet/purple
      icon: ArrowUpRight,
      trend: metrics.conversion_rate > 5 ? 'up' as const : 'neutral' as const,
    },
    {
      label: 'Churns 30j',
      value: String(metrics.churns_30d),
      sub: `résiliations ce mois`,
      color: metrics.churns_30d > 0 ? '#f87171' : '#64748b',   // red ou slate
      icon: Zap,
      trend: metrics.churns_30d > 0 ? 'down' as const : 'neutral' as const,
    },
    {
      label: 'Inscrits 30j',
      value: String(metrics.new_signups_30d),
      sub: `nouveaux comptes`,
      color: '#fbbf24',   // amber/yellow
      icon: UserPlus,
      trend: metrics.new_signups_30d > 0 ? 'up' as const : 'neutral' as const,
    },
    {
      label: 'Actifs 7j',
      value: String(metrics.active_users_7d),
      sub: `users avec ≥1 scan`,
      color: '#38bdf8',   // sky
      icon: Users,
      trend: 'neutral' as const,
    },
  ];

  return (
    <div className="space-y-6">
      {/* KPI Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {kpis.map(k => (
          <KpiCard key={k.label} {...k} />
        ))}
      </div>

      {/* Plan breakdown + Sparklines */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">

        {/* Plan breakdown */}
        <div className="sku-card rounded-xl p-5">
          <div className="flex items-center gap-2 mb-4">
            <BarChart3 size={14} className="text-slate-500" />
            <h3 className="text-white text-sm font-bold">Répartition des plans</h3>
          </div>
          <div className="space-y-3">
            {(['free', 'starter', 'pro', 'dev', 'team'] as const).map(plan => {
              const count = metrics.plan_breakdown[plan] ?? 0;
              const pct   = Math.round((count / totalPlanUsers) * 100);
              const labels: Record<string, string> = { free: 'Free', starter: 'Starter', pro: 'Pro', dev: 'Dev', team: 'Team' };
              const barColor = PLAN_BAR_COLORS[plan] ?? 'bg-slate-600';
              return (
                <div key={plan}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs text-slate-400 font-mono">{labels[plan]}</span>
                    <span className="text-xs text-slate-300 font-mono font-bold">{count} <span className="text-slate-600">({pct}%)</span></span>
                  </div>
                  <div className="h-1.5 sku-progress-track rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-700 ${barColor}`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
          <div className="mt-4 pt-4 grid grid-cols-2 gap-2" style={{ borderTop: '1px solid var(--color-border)' }}>
            <div className="text-center">
              <p className="text-white font-black font-mono text-lg">{stats.total_users}</p>
              <p className="text-slate-600 text-[10px] font-mono">total inscrits</p>
            </div>
            <div className="text-center">
              <p className="text-white font-black font-mono text-lg">{stats.total_scans}</p>
              <p className="text-slate-600 text-[10px] font-mono">scans total</p>
            </div>
          </div>
        </div>

        {/* Sparkline charts */}
        <div className="space-y-4">
          {/* Signups 30d */}
          <div className="sku-card rounded-xl p-5">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <UserPlus size={13} className="text-yellow-400" />
                <h3 className="text-white text-sm font-bold">Inscrits — 30 jours</h3>
              </div>
              <span className="text-yellow-400 font-mono font-black text-sm">+{metrics.new_signups_30d}</span>
            </div>
            <Sparkline data={metrics.signups_last_30d} color="#eab308" width={260} height={52} />
          </div>

          {/* Scans 14d */}
          <div className="sku-card rounded-xl p-5">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Zap size={13} className="text-cyan-400" />
                <h3 className="text-white text-sm font-bold">Scans — 14 jours</h3>
              </div>
              <span className="text-cyan-400 font-mono font-black text-sm">
                {metrics.scans_last_14d.reduce((a, b) => a + b.count, 0)}
              </span>
            </div>
            <Sparkline data={metrics.scans_last_14d} color="#06b6d4" width={260} height={52} />
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Users Tab ────────────────────────────────────────────────────────────────

function UsersTab({
  users,
  stats,
  updating,
  onUpdatePlan,
  onToggleActive,
  onDelete,
  onReset2FA,
}: {
  users: UserAdmin[];
  stats: Stats | null;
  updating: number | null;
  onUpdatePlan: (id: number, plan: string) => void;
  onToggleActive: (id: number, active: boolean) => void;
  onDelete: (id: number, email: string) => void;
  onReset2FA: (id: number, email: string) => void;
}) {
  const { user } = useAuth();
  const [search, setSearch] = useState('');

  const filtered = users.filter(u =>
    u.email.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div>
      {/* Stats row */}
      {stats && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-5"
        >
          {[
            { label: 'Total', value: stats.total_users, color: 'text-white' },
            { label: 'Actifs', value: stats.active_users, color: 'text-emerald-400' },
            { label: 'Free', value: stats.free_users, color: 'text-slate-400' },
            { label: 'Payants', value: stats.pro_users, color: 'text-cyan-400' },
            { label: 'Scans', value: stats.total_scans, color: 'text-purple-400' },
          ].map(s => (
            <div key={s.label} className="sku-stat rounded-xl">
              <p className={`text-xl font-black font-mono ${s.color}`}>{s.value}</p>
              <p className="text-slate-600 text-[10px] font-mono mt-0.5">{s.label}</p>
            </div>
          ))}
        </motion.div>
      )}

      {/* Search */}
      <div className="mb-4">
        <input
          type="text"
          placeholder="Rechercher un email…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="w-full sm:w-72 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-1 focus:ring-cyan-500/40 transition sku-inset"
          style={{ border: '1px solid rgba(255,255,255,0.08)' }}
        />
      </div>

      {/* Table */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="sku-panel rounded-2xl overflow-hidden"
      >
        <table className="w-full">
          <thead>
            <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
              <th className="text-left px-4 py-3 text-[10px] text-slate-500 font-mono uppercase tracking-wider">Email</th>
              <th className="text-left px-4 py-3 text-[10px] text-slate-500 font-mono uppercase tracking-wider">Plan</th>
              <th className="text-left px-4 py-3 text-[10px] text-slate-500 font-mono uppercase tracking-wider hidden sm:table-cell">Scans</th>
              <th className="text-left px-4 py-3 text-[10px] text-slate-500 font-mono uppercase tracking-wider hidden md:table-cell">Inscrit</th>
              <th className="text-left px-4 py-3 text-[10px] text-slate-500 font-mono uppercase tracking-wider">Statut</th>
              <th className="text-left px-4 py-3 text-[10px] text-slate-500 font-mono uppercase tracking-wider hidden lg:table-cell">2FA</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={6} className="text-center py-12 text-slate-700 font-mono text-xs">
                  Aucun utilisateur
                </td>
              </tr>
            ) : filtered.map(u => (
              <tr
                key={u.id}
                className={`transition ${updating === u.id ? 'opacity-50 pointer-events-none' : ''}`}
                style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}
                onMouseEnter={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.025)')}
                onMouseLeave={e => (e.currentTarget.style.background = '')}
              >
                {/* Email */}
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <div className="w-7 h-7 rounded-full bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400 text-xs font-bold shrink-0">
                      {u.email[0].toUpperCase()}
                    </div>
                    <div className="flex flex-col">
                      <span className="text-xs text-slate-300 font-mono truncate max-w-[180px]">{u.email}</span>
                      {u.is_admin && (
                        <span className="text-[9px] text-yellow-500 font-mono">admin</span>
                      )}
                    </div>
                  </div>
                </td>

                {/* Plan */}
                <td className="px-4 py-3">
                  <select
                    value={u.plan}
                    onChange={e => onUpdatePlan(u.id, e.target.value)}
                    disabled={updating === u.id || u.id === user?.id}
                    className={`text-xs font-mono px-2 py-1 rounded-lg border cursor-pointer focus:outline-none transition bg-transparent disabled:cursor-not-allowed ${PLAN_COLORS[u.plan] ?? PLAN_COLORS.free}`}
                  >
                    <option value="free"    className="bg-slate-900 text-slate-400">Free</option>
                    <option value="starter" className="bg-slate-900 text-emerald-400">Starter</option>
                    <option value="pro"     className="bg-slate-900 text-cyan-400">Pro</option>
                    <option value="dev"     className="bg-slate-900 text-violet-400">Dev</option>
                  </select>
                </td>

                {/* Scans */}
                <td className="px-4 py-3 hidden sm:table-cell">
                  <span className="text-xs text-slate-400 font-mono">{u.scan_count}</span>
                </td>

                {/* Date */}
                <td className="px-4 py-3 hidden md:table-cell">
                  <span className="text-xs text-slate-500 font-mono">
                    {new Date(u.created_at).toLocaleDateString('fr-FR')}
                  </span>
                </td>

                {/* Statut */}
                <td className="px-4 py-3">
                  <button
                    onClick={() => onToggleActive(u.id, !u.is_active)}
                    disabled={updating === u.id || u.id === user?.id}
                    title={u.is_active ? 'Désactiver' : 'Activer'}
                    className="disabled:cursor-not-allowed"
                  >
                    {u.is_active
                      ? <CheckCircle size={16} className="text-emerald-400 hover:text-emerald-300 transition" />
                      : <XCircle    size={16} className="text-red-400 hover:text-red-300 transition" />
                    }
                  </button>
                </td>

                {/* 2FA */}
                <td className="px-4 py-3 hidden lg:table-cell">
                  {u.mfa_enabled ? (
                    <span className="inline-flex items-center gap-1 text-[10px] font-mono text-green-400 bg-green-500/10 border border-green-500/20 px-1.5 py-0.5 rounded">
                      <svg width="8" height="8" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>
                      ON
                    </span>
                  ) : (
                    <span className="text-[10px] font-mono text-slate-600">—</span>
                  )}
                </td>

                {/* Actions : reset 2FA + suppression */}
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    {u.mfa_enabled && (
                      <button
                        onClick={() => onReset2FA(u.id, u.email)}
                        disabled={updating === u.id}
                        className="text-slate-600 hover:text-amber-400 transition disabled:cursor-not-allowed"
                        title="Réinitialiser la 2FA"
                      >
                        <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                      </button>
                    )}
                    {u.id !== user?.id && !u.is_admin && (
                      <button
                        onClick={() => onDelete(u.id, u.email)}
                        disabled={updating === u.id}
                        className="text-slate-700 hover:text-red-400 transition disabled:cursor-not-allowed"
                        title="Supprimer"
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </motion.div>
    </div>
  );
}

// ─── Blog Links Tab ───────────────────────────────────────────────────────────

function BlogLinksTab({ links, onRefresh }: { links: BlogLink[]; onRefresh: () => void }) {
  const [form, setForm]       = useState({ match_keyword: '', article_title: '', article_url: '' });
  const [editId, setEditId]   = useState<number | null>(null);
  const [editForm, setEditForm] = useState({ match_keyword: '', article_title: '', article_url: '' });
  const [saving, setSaving]   = useState(false);
  const [error, setError]     = useState('');

  const resetForm = () => setForm({ match_keyword: '', article_title: '', article_url: '' });

  const handleCreate = async () => {
    if (!form.match_keyword.trim() || !form.article_title.trim() || !form.article_url.trim()) return;
    setSaving(true); setError('');
    try {
      await apiClient.post('/admin/blog-links', form);
      resetForm();
      onRefresh();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Erreur');
    } finally { setSaving(false); }
  };

  const handleEdit = (link: BlogLink) => {
    setEditId(link.id);
    setEditForm({ match_keyword: link.match_keyword, article_title: link.article_title, article_url: link.article_url });
  };

  const handleSaveEdit = async () => {
    if (!editId) return;
    setSaving(true); setError('');
    try {
      await apiClient.put(`/admin/blog-links/${editId}`, editForm);
      setEditId(null);
      onRefresh();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Erreur');
    } finally { setSaving(false); }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Supprimer ce lien ?')) return;
    try {
      await apiClient.delete(`/admin/blog-links/${id}`);
      onRefresh();
    } catch (e: any) {
      alert(e?.response?.data?.detail || 'Erreur');
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <SkuIcon color="#a78bfa" size={36}>
          <BookOpen size={16} className="text-violet-300" />
        </SkuIcon>
        <div>
          <h2 className="text-sm font-bold text-slate-100">Liens articles de blog</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Associez un ou plusieurs mots-clés (séparés par des virgules) à un article. Si la recommandation contient l'un des mots-clés, le lien s'affiche automatiquement.
          </p>
        </div>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3 text-red-400 text-xs">{error}</div>
      )}

      {/* Formulaire d'ajout */}
      <div className="sku-card rounded-xl p-5 space-y-3">
        <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Ajouter un lien</p>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div>
            <label className="text-[10px] text-slate-500 uppercase tracking-wider block mb-1">Mot-clé</label>
            <input
              className="sku-inset w-full rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-600"
              placeholder="ex: SPF, DMARC, enregistrement DNS"
              value={form.match_keyword}
              onChange={e => setForm(f => ({ ...f, match_keyword: e.target.value }))}
            />
          </div>
          <div>
            <label className="text-[10px] text-slate-500 uppercase tracking-wider block mb-1">Titre de l'article</label>
            <input
              className="sku-inset w-full rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-600"
              placeholder="Comment configurer SPF"
              value={form.article_title}
              onChange={e => setForm(f => ({ ...f, article_title: e.target.value }))}
            />
          </div>
          <div>
            <label className="text-[10px] text-slate-500 uppercase tracking-wider block mb-1">URL de l'article</label>
            <input
              className="sku-inset w-full rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-600"
              placeholder="https://wezea.net/blog/…"
              value={form.article_url}
              onChange={e => setForm(f => ({ ...f, article_url: e.target.value }))}
            />
          </div>
        </div>
        <button
          onClick={handleCreate}
          disabled={saving || !form.match_keyword.trim() || !form.article_title.trim() || !form.article_url.trim()}
          className="sku-btn-primary flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium disabled:opacity-40"
        >
          <Plus size={12} />
          Ajouter
        </button>
      </div>

      {/* Liste */}
      {links.length === 0 ? (
        <div className="flex flex-col items-center gap-3 py-12 text-center sku-card rounded-xl">
          <BookOpen size={28} className="text-slate-700" />
          <p className="text-slate-500 text-sm">Aucun lien configuré</p>
          <p className="text-slate-600 text-xs max-w-xs">Ajoutez un lien ci-dessus pour qu'il apparaisse dans l'onglet Recommandations des scans.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {links.map(link => (
            <div key={link.id} className="sku-card rounded-xl p-4">
              {editId === link.id ? (
                /* Mode édition */
                <div className="space-y-3">
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <input
                      className="sku-inset rounded-lg px-3 py-2 text-xs text-slate-200"
                      value={editForm.match_keyword}
                      onChange={e => setEditForm(f => ({ ...f, match_keyword: e.target.value }))}
                      placeholder="Mot-clé"
                    />
                    <input
                      className="sku-inset rounded-lg px-3 py-2 text-xs text-slate-200"
                      value={editForm.article_title}
                      onChange={e => setEditForm(f => ({ ...f, article_title: e.target.value }))}
                      placeholder="Titre"
                    />
                    <input
                      className="sku-inset rounded-lg px-3 py-2 text-xs text-slate-200"
                      value={editForm.article_url}
                      onChange={e => setEditForm(f => ({ ...f, article_url: e.target.value }))}
                      placeholder="URL"
                    />
                  </div>
                  <div className="flex gap-2">
                    <button onClick={handleSaveEdit} disabled={saving} className="sku-btn-primary px-3 py-1.5 rounded-lg text-xs font-medium disabled:opacity-40">
                      Enregistrer
                    </button>
                    <button onClick={() => setEditId(null)} className="sku-btn-ghost px-3 py-1.5 rounded-lg text-xs">
                      Annuler
                    </button>
                  </div>
                </div>
              ) : (
                /* Mode lecture */
                <div className="flex items-center gap-3">
                  <span className="shrink-0 px-2 py-0.5 rounded-md bg-violet-500/15 border border-violet-500/25 text-violet-300 text-[10px] font-mono font-bold">
                    {link.match_keyword}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-slate-200 text-xs font-medium truncate">{link.article_title}</p>
                    <a href={link.article_url} target="_blank" rel="noopener noreferrer"
                      className="text-[10px] text-slate-500 hover:text-cyan-400 transition truncate flex items-center gap-1 mt-0.5">
                      <ExternalLink size={9} />
                      {link.article_url}
                    </a>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <button onClick={() => handleEdit(link)} className="text-slate-600 hover:text-slate-300 transition" title="Modifier">
                      <Pencil size={13} />
                    </button>
                    <button onClick={() => handleDelete(link.id)} className="text-slate-600 hover:text-red-400 transition" title="Supprimer">
                      <X size={13} />
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Main AdminPage ───────────────────────────────────────────────────────────

export default function AdminPage({ onBack, onGoHistory, onGoClientSpace, onGoContact }: Props) {
  const [tab,        setTab]        = useState<Tab>('metrics');
  const [metrics,    setMetrics]    = useState<Metrics | null>(null);
  const [users,      setUsers]      = useState<UserAdmin[]>([]);
  const [stats,      setStats]      = useState<Stats | null>(null);
  const [blogLinks,  setBlogLinks]  = useState<BlogLink[]>([]);
  const [perf,       setPerf]       = useState<PerfStats | null>(null);
  const [loading,    setLoading]    = useState(true);
  const [error,      setError]      = useState('');
  const [updating,   setUpdating]   = useState<number | null>(null);

  const fetchPerf = async () => {
    try {
      const res = await apiClient.get('/admin/metrics/performance');
      setPerf(res.data);
    } catch { /* silencieux */ }
  };

  const fetchData = async () => {
    setLoading(true);
    setError('');
    try {
      const [usersRes, statsRes, metricsRes, blogRes, perfRes] = await Promise.all([
        apiClient.get('/admin/users'),
        apiClient.get('/admin/stats'),
        apiClient.get('/admin/metrics'),
        apiClient.get('/admin/blog-links'),
        apiClient.get('/admin/metrics/performance'),
      ]);
      setUsers(usersRes.data);
      setStats(statsRes.data);
      setMetrics(metricsRes.data);
      setBlogLinks(blogRes.data);
      setPerf(perfRes.data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Erreur de chargement');
    } finally {
      setLoading(false);
    }
  };

  const fetchBlogLinks = async () => {
    try {
      const res = await apiClient.get('/admin/blog-links');
      setBlogLinks(res.data);
    } catch { /* silencieux */ }
  };

  useEffect(() => { fetchData(); }, []);

  const updatePlan = async (userId: number, plan: string) => {
    setUpdating(userId);
    try {
      const res = await apiClient.patch(`/admin/users/${userId}`, { plan });
      setUsers(prev => prev.map(u => u.id === userId ? res.data : u));
      // Refresh stats/metrics silently
      Promise.all([
        apiClient.get('/admin/stats'),
        apiClient.get('/admin/metrics'),
      ]).then(([s, m]) => { setStats(s.data); setMetrics(m.data); }).catch(() => {});
    } catch (e: any) {
      alert(e?.response?.data?.detail || 'Erreur');
    } finally {
      setUpdating(null);
    }
  };

  const toggleActive = async (userId: number, is_active: boolean) => {
    setUpdating(userId);
    try {
      const res = await apiClient.patch(`/admin/users/${userId}`, { is_active });
      setUsers(prev => prev.map(u => u.id === userId ? res.data : u));
    } catch (e: any) {
      alert(e?.response?.data?.detail || 'Erreur');
    } finally {
      setUpdating(null);
    }
  };

  const deleteUser = async (userId: number, email: string) => {
    if (!confirm(`Supprimer ${email} et tout son historique ?`)) return;
    setUpdating(userId);
    try {
      await apiClient.delete(`/admin/users/${userId}`);
      setUsers(prev => prev.filter(u => u.id !== userId));
    } catch (e: any) {
      alert(e?.response?.data?.detail || 'Erreur');
    } finally {
      setUpdating(null);
    }
  };

  const reset2FA = async (userId: number, email: string) => {
    if (!confirm(`Réinitialiser la 2FA de ${email} ?`)) return;
    setUpdating(userId);
    try {
      await apiClient.post(`/admin/users/${userId}/reset-2fa`);
      setUsers(prev => prev.map(u => u.id === userId ? { ...u, mfa_enabled: false } : u));
    } catch (e: any) {
      alert(e?.response?.data?.detail || 'Erreur');
    } finally {
      setUpdating(null);
    }
  };

  return (
    <div className="relative min-h-screen text-slate-100">
      {/* Grille cyber — identique au hero Dashboard */}
      <div className="absolute inset-0 pointer-events-none" style={{ backgroundImage: 'linear-gradient(rgba(34,211,238,1) 1px, transparent 1px), linear-gradient(90deg, rgba(34,211,238,1) 1px, transparent 1px)', backgroundSize: '48px 48px', opacity: 0.025 }} />

      {/* Nav */}
      <PageNavbar
        onBack={onBack ?? (() => {})}
        title="Admin"
        icon={<Shield size={14} />}
        onGoHistory={onGoHistory}
        onGoClientSpace={onGoClientSpace}
        onGoContact={onGoContact}
        actions={
          <button
            onClick={fetchData}
            className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-200 transition px-3 py-1.5 rounded-lg hover:bg-white/5 border border-white/6 font-medium"
          >
            <RefreshCw size={11} className={loading ? 'animate-spin' : ''} />
            Actualiser
          </button>
        }
      />

      <div className="max-w-6xl mx-auto px-4 py-6">

        {/* Tab bar */}
        <div className="flex gap-1 mb-6 sku-panel rounded-xl p-1 w-fit">
          {([
            { key: 'metrics',     label: 'Métriques',     icon: TrendingUp },
            { key: 'performance', label: 'Performance',   icon: Activity  },
            { key: 'users',       label: 'Utilisateurs',  icon: Users     },
            { key: 'blog',        label: 'Blog',          icon: BookOpen  },
          ] as { key: Tab; label: string; icon: React.ElementType }[]).map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium transition ${
                tab === key
                  ? 'text-white'
                  : 'text-slate-500 hover:text-slate-300'
              }`}
            >
              <Icon size={13} />
              {label}
              {key === 'users' && users.length > 0 && (
                <span className="ml-0.5 bg-slate-700 text-slate-300 rounded-full px-1.5 py-0.5 text-[9px] font-mono">
                  {users.length}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Error */}
        {error && (
          <div className="mb-5 bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3 text-red-400 text-xs">
            {error}
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="flex items-center justify-center py-20">
            <div className="w-6 h-6 border-2 border-cyan-500/30 border-t-cyan-500 rounded-full animate-spin" />
          </div>
        )}

        {/* Content */}
        {!loading && (
          <>
            {tab === 'metrics' && (
              <MetricsTab metrics={metrics} stats={stats} />
            )}
            {tab === 'performance' && (
              <PerformanceTab perf={perf} onRefresh={fetchPerf} />
            )}
            {tab === 'users' && (
              <UsersTab
                users={users}
                stats={stats}
                updating={updating}
                onUpdatePlan={updatePlan}
                onToggleActive={toggleActive}
                onDelete={deleteUser}
                onReset2FA={reset2FA}
              />
            )}
            {tab === 'blog' && (
              <BlogLinksTab links={blogLinks} onRefresh={fetchBlogLinks} />
            )}
          </>
        )}
      </div>
    </div>
  );
}
