/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        mono: ['"JetBrains Mono"', '"Fira Code"', '"Cascadia Code"', 'monospace'],
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
      },
      colors: {
        // Palette cyber étendue
        cyber: {
          50:  '#ecfeff',
          100: '#cffafe',
          200: '#a5f3fc',
          300: '#67e8f9',
          400: '#22d3ee',
          500: '#06b6d4',
          600: '#0891b2',
          700: '#0e7490',
          800: '#155e75',
          900: '#164e63',
          950: '#083344',
        },
      },
      animation: {
        'pulse-slow':   'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'blink':        'blink 1s step-end infinite',
        'scan-line':    'scan-line 2s linear infinite',
      },
      keyframes: {
        blink: {
          '0%, 100%': { opacity: '1' },
          '50%':      { opacity: '0' },
        },
        'scan-line': {
          '0%':   { transform: 'translateY(-100%)' },
          '100%': { transform: 'translateY(100%)' },
        },
      },
      boxShadow: {
        'cyan-glow':   '0 0 20px rgba(14, 165, 233, 0.3)',
        'red-glow':    '0 0 20px rgba(239, 68, 68, 0.3)',
        'green-glow':  '0 0 20px rgba(34, 197, 94, 0.3)',
        'orange-glow': '0 0 20px rgba(249, 115, 22, 0.3)',
      },
      backgroundImage: {
        'grid-cyber': `
          linear-gradient(rgba(14,165,233,0.05) 1px, transparent 1px),
          linear-gradient(90deg, rgba(14,165,233,0.05) 1px, transparent 1px)
        `,
      },
      backgroundSize: {
        'grid-40': '40px 40px',
      },
    },
  },
  plugins: [],
};
