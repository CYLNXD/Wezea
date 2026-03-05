import { createContext, useContext, useState, useEffect, ReactNode } from 'react';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export interface AuthUser {
  id: number;
  email: string;
  plan: 'free' | 'pro' | 'team';
  api_key: string | null;
}

interface AuthContextType {
  user: AuthUser | null;
  token: string | null;
  loading: boolean;
  login:    (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout:   () => void;
  authHeaders: () => Record<string, string>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user,    setUser]    = useState<AuthUser | null>(null);
  const [token,   setToken]   = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Restore session on mount
  useEffect(() => {
    const saved = localStorage.getItem('wezea_token');
    if (saved) {
      setToken(saved);
      fetchMe(saved).finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  async function fetchMe(t: string) {
    try {
      const res = await fetch(`${API}/auth/me`, {
        headers: { Authorization: `Bearer ${t}` },
      });
      if (res.ok) {
        const data = await res.json();
        setUser({ id: data.id, email: data.email, plan: data.plan, api_key: data.api_key });
      } else {
        logout();
      }
    } catch {
      logout();
    }
  }

  async function login(email: string, password: string) {
    const res = await fetch(`${API}/auth/login`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Erreur de connexion');
    }
    const data = await res.json();
    localStorage.setItem('wezea_token', data.access_token);
    setToken(data.access_token);
    setUser(data.user);
  }

  async function register(email: string, password: string) {
    const res = await fetch(`${API}/auth/register`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Erreur lors de l\'inscription');
    }
    const data = await res.json();
    localStorage.setItem('wezea_token', data.access_token);
    setToken(data.access_token);
    setUser(data.user);
  }

  function logout() {
    localStorage.removeItem('wezea_token');
    setToken(null);
    setUser(null);
  }

  function authHeaders(): Record<string, string> {
    return token ? { Authorization: `Bearer ${token}` } : {};
  }

  return (
    <AuthContext.Provider value={{ user, token, loading, login, register, logout, authHeaders }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
