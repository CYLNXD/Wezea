import { Component, type ErrorInfo, type ReactNode } from 'react';
import { AlertTriangle, RotateCcw } from 'lucide-react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

/**
 * ErrorBoundary — attrape les erreurs React non gérées et affiche
 * un écran de secours au lieu d'un écran blanc.
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Log en dev uniquement
    if (import.meta.env.DEV) {
      console.error('[ErrorBoundary]', error, info.componentStack);
    }
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  handleReload = () => {
    window.location.href = '/';
  };

  render() {
    if (!this.state.hasError) return this.props.children;

    return (
      <div className="min-h-screen flex items-center justify-center px-6"
        style={{ background: '#0b1120' }}
      >
        <div className="max-w-md w-full text-center flex flex-col items-center gap-5">
          <div className="w-16 h-16 rounded-2xl flex items-center justify-center"
            style={{
              background: 'linear-gradient(150deg, rgba(248,113,113,0.2) 0%, rgba(248,113,113,0.05) 100%)',
              border: '1px solid rgba(248,113,113,0.3)',
              boxShadow: '0 4px 16px rgba(248,113,113,0.15)',
            }}
          >
            <AlertTriangle size={28} className="text-red-400" />
          </div>

          <div>
            <h2 className="text-white text-lg font-bold">
              Une erreur inattendue est survenue
            </h2>
            <p className="text-slate-400 text-sm mt-2 leading-relaxed">
              L'application a rencontré un problème. Vous pouvez réessayer ou
              revenir à l'accueil.
            </p>
          </div>

          {import.meta.env.DEV && this.state.error && (
            <pre className="text-left text-xs text-red-300/70 bg-red-950/30 border border-red-900/30 rounded-lg p-3 max-h-32 overflow-auto w-full">
              {this.state.error.message}
            </pre>
          )}

          <div className="flex gap-3">
            <button
              onClick={this.handleRetry}
              className="sku-btn-ghost text-sm px-4 py-2 rounded-xl flex items-center gap-2"
            >
              <RotateCcw size={14} />
              Réessayer
            </button>
            <button
              onClick={this.handleReload}
              className="sku-btn-primary text-sm px-4 py-2 rounded-xl"
            >
              Retour à l'accueil
            </button>
          </div>
        </div>
      </div>
    );
  }
}
