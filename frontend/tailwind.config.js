/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // One palette, used by both the UI chrome and the graph node styles,
        // so a "flagged" pill and a flagged node are always the same red.
        ink: {
          950: '#0a0e17',
          900: '#0f1420',
          850: '#141b2a',
          800: '#1a2334',
          700: '#243045',
          600: '#33415c',
          500: '#4a5a78',
        },
        risk: {
          safe: '#34d399',
          suspicious: '#fbbf24',
          flagged: '#f43f5e',
        },
        entity: {
          device: '#38bdf8',
          ip: '#a78bfa',
          card: '#94a3b8',
          customer: '#2dd4bf',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },
      fontSize: {
        '2xs': ['0.6875rem', { lineHeight: '1rem', letterSpacing: '0.02em' }],
      },
      keyframes: {
        shimmer: { '100%': { transform: 'translateX(100%)' } },
        'fade-up': {
          '0%': { opacity: '0', transform: 'translateY(4px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        shimmer: 'shimmer 1.6s infinite',
        'fade-up': 'fade-up 0.25s ease-out',
      },
    },
  },
  plugins: [],
}
