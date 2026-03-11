// ─── WezeaLogo — logo partagé du site ────────────────────────────────────────
// Usage :
//   <WezeaLogo />                   — compact (CompliancePage, PublicScanPage)
//   <WezeaLogo size="md" showSub />  — moyen avec sous-titre (PageNavbar)
//   <WezeaLogo size="lg" showSub />  — grand avec sous-titre (Dashboard)
import { Shield } from 'lucide-react';

interface Props {
  /** Taille de l'icône-boîte et du texte */
  size?:    'sm' | 'md' | 'lg';
  /** Affiche "Security Scanner" sous le nom */
  showSub?: boolean;
  /** Classes supplémentaires sur le wrapper */
  className?: string;
}

const CONFIG = {
  sm: { box: 'w-6 h-6 rounded-lg',  icon: 12, text: 'text-sm',  gap: 'gap-2',   sub: 'text-[9px]'  },
  md: { box: 'w-7 h-7 rounded-xl',  icon: 14, text: 'text-base', gap: 'gap-2.5', sub: 'text-[9px]'  },
  lg: { box: 'w-8 h-8 rounded-xl',  icon: 16, text: 'text-lg',  gap: 'gap-2.5', sub: 'text-[9px]'  },
} as const;

export default function WezeaLogo({ size = 'sm', showSub = false, className = '' }: Props) {
  const c = CONFIG[size];
  return (
    <div className={`flex items-center ${c.gap} ${className}`}>
      {/* Icône-boîte skeuomorphique */}
      <div
        className={`${c.box} flex-shrink-0 flex items-center justify-center relative overflow-hidden`}
        style={{
          background: 'linear-gradient(150deg, rgba(34,211,238,0.20) 0%, rgba(34,211,238,0.06) 100%)',
          border:     '1px solid rgba(34,211,238,0.32)',
          boxShadow:  '0 2px 8px rgba(34,211,238,0.14), inset 0 1px 0 rgba(34,211,238,0.22), inset 0 -1px 0 rgba(0,0,0,0.2)',
        }}
      >
        {/* Reflet supérieur */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            borderRadius: 'inherit',
            background: 'linear-gradient(180deg,rgba(255,255,255,0.07) 0%,transparent 50%)',
          }}
        />
        <Shield size={c.icon} className="text-cyan-400 relative z-10" />
      </div>

      {/* Texte */}
      <div className="flex flex-col leading-none text-left">
        <span
          className={`font-black tracking-tight text-white leading-none ${c.text}`}
          style={{ letterSpacing: '-0.03em' }}
        >
          Wezea
        </span>
        {showSub && (
          <span
            className={`${c.sub} uppercase text-slate-500 mt-0.5 hidden sm:block`}
            style={{ letterSpacing: '0.12em', fontWeight: 500 }}
          >
            Security Scanner
          </span>
        )}
      </div>
    </div>
  );
}
