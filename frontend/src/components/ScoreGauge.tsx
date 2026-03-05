// ─── ScoreGauge — Jauge circulaire SVG animée ─────────────────────────────────
import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Shield, ShieldAlert, ShieldCheck, ShieldX } from 'lucide-react';
import { useLanguage } from '../i18n/LanguageContext';
import { scoreColor } from '../types/scanner';
import type { RiskLevel } from '../types/scanner';

interface Props {
  score:     number;
  riskLevel: RiskLevel;
  domain:    string;
}

const RISK_KEYS: Record<RiskLevel, string> = {
  CRITICAL: 'risk_critical',
  HIGH:     'risk_high',
  MEDIUM:   'risk_medium',
  LOW:      'risk_low',
};

const RISK_ICONS: Record<RiskLevel, typeof Shield> = {
  CRITICAL: ShieldX,
  HIGH:     ShieldAlert,
  MEDIUM:   ShieldAlert,
  LOW:      ShieldCheck,
};

// ── Constantes SVG ────────────────────────────────────────────────────────────
const SIZE         = 220;
const STROKE_WIDTH = 14;
const RADIUS       = (SIZE - STROKE_WIDTH) / 2;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

// Arc part de -215° pour former un arc ouvert en bas (270° d'ouverture)
const ARC_RATIO    = 0.75;   // 270° / 360°
const ARC_GAP      = CIRCUMFERENCE * (1 - ARC_RATIO);
const START_ANGLE  = 135;    // degrés — le gap est en bas

export function ScoreGauge({ score, riskLevel, domain }: Props) {
  const { t } = useLanguage();
  const [displayScore, setDisplayScore] = useState(0);

  // Animation du compteur numérique (count-up)
  useEffect(() => {
    let frame: number;
    const duration = 1400; // ms
    const start    = performance.now();

    const tick = (now: number) => {
      const t       = Math.min((now - start) / duration, 1);
      const eased   = 1 - Math.pow(1 - t, 3); // ease-out-cubic
      setDisplayScore(Math.round(eased * score));
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [score]);

  const colors = scoreColor(score);
  const RiskIcon = RISK_ICONS[riskLevel];

  // Longueur de l'arc rempli
  const fillLength = CIRCUMFERENCE * ARC_RATIO * (score / 100);
  // dasharray: arc rempli + reste du cercle ; dashoffset: rotation pour commencer à START_ANGLE
  const dashArray  = `${fillLength} ${CIRCUMFERENCE - fillLength + ARC_GAP}`;
  // On tourne le cercle de START_ANGLE pour placer le début du trait au bon endroit
  const rotation   = `rotate(${START_ANGLE}, ${SIZE / 2}, ${SIZE / 2})`;

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.5, ease: 'easeOut' }}
      className="flex flex-col items-center gap-4"
    >
      {/* Jauge SVG avec bezel skeuomorphique */}
      <div
        className="relative sku-gauge-bezel flex items-center justify-center"
        style={{ width: SIZE + 20, height: SIZE + 20, padding: '10px' }}
      >
        <div className="relative" style={{ width: SIZE, height: SIZE }}>
        <svg width={SIZE} height={SIZE} className="overflow-visible">
          <defs>
            <filter id="glow">
              <feGaussianBlur stdDeviation="4" result="coloredBlur" />
              <feMerge>
                <feMergeNode in="coloredBlur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          {/* Arc de fond (gris) */}
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={RADIUS}
            fill="none"
            stroke="#1e293b"
            strokeWidth={STROKE_WIDTH}
            strokeLinecap="round"
            strokeDasharray={`${CIRCUMFERENCE * ARC_RATIO} ${CIRCUMFERENCE * (1 - ARC_RATIO)}`}
            transform={rotation}
          />

          {/* Arc de score (coloré + animé) */}
          <motion.circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={RADIUS}
            fill="none"
            stroke={colors.gauge}
            strokeWidth={STROKE_WIDTH}
            strokeLinecap="round"
            strokeDasharray={dashArray}
            transform={rotation}
            filter="url(#glow)"
            initial={{ strokeDasharray: `0 ${CIRCUMFERENCE}` }}
            animate={{ strokeDasharray: dashArray }}
            transition={{ duration: 1.4, ease: [0.34, 1.56, 0.64, 1] }}
          />
        </svg>

        {/* Contenu central */}
        <div className="absolute inset-0 flex flex-col items-center justify-center pb-4 z-10">
          <motion.span
            className="font-mono font-black leading-none text-glow-green"
            style={{
              fontSize:   '3.5rem',
              color:      colors.gauge,
              textShadow: colors.glow,
            }}
          >
            {displayScore}
          </motion.span>
          <span className="text-slate-500 text-xs font-mono mt-1">/ 100</span>
          <div className="flex items-center gap-1.5 mt-2">
            <RiskIcon size={14} style={{ color: colors.gauge }} />
            <span className="text-sm font-semibold" style={{ color: colors.gauge }}>
              {colors.label}
            </span>
          </div>
        </div>
        </div>{/* end gauge inner */}
      </div>{/* end bezel */}

      {/* Légende sous la jauge */}
      <div className="text-center">
        <p className="text-slate-300 font-semibold text-base">
          Niveau de risque : <span className={`font-bold ${colors.textClass}`}>
            {t(RISK_KEYS[riskLevel] as any)}
          </span>
        </p>
        <p className="text-slate-500 text-xs font-mono mt-1">{domain}</p>
      </div>

      {/* Légende de l'échelle */}
      <div className="flex items-center gap-3 text-xs font-mono text-slate-500">
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-red-500" style={{ boxShadow: '0 0 5px rgba(239,68,68,0.7)' }} /> {t('gauge_scale_bad')}
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-orange-500" /> {t('gauge_scale_mid')}
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-green-500" /> {t('gauge_scale_good')}
        </span>
      </div>
    </motion.div>
  );
}
