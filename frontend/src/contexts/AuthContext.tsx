import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import axios from 'axios';
import { analyticsIdentify, analyticsReset } from '../lib/analytics';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const authApi = axios.create({ baseURL: API, headers: { 'Content-Type': 'application/json' } });
export const paymentApi = authApi;

export interface AuthUser {
  id: number;
  email: string;
  plan: 'free' | 'starter' | 'pro' | 'dev' | 'team';
  api_key: string | null;
  first_name: string | null;
  last_name: string | null;
  google_id: string | null;
  is_admin: boolean;
  mfa_enabled: boolean;
}

interface AuthContextType {
  user: AuthUser | null;
  token: string | null;
  loading: boolean;
  login:           (email: string, password: string) => Promise<void>;
  loginWithToken:  (token: string, userData: Partial<AuthUser>) => void;
  register:        (email: string, password: string) => Promise<void>;
  googleLogin:     (idToken: string) => Promise<{ mfa_required?: boolean; mfa_token?: string }>;
  logout:          () => void;
  authHeaders:     () => Record<string, string>;
  updateProfile:   (first_name: string | null, last_name: string | null) => Promise<void>;
  deleteAccount:   (password: string) => Promise<void>;
  upgradeToPlan:   (plan: 'starter' | 'pro' | 'dev') => Promise<string>;  // retourne checkout_url Stripe
  getPortalUrl:    () => Promise<string>;                          // retourne portal_url Stripe
  refreshUser:     () => Promise<void>;
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
      const { data } = await authApi.get('/auth/me', {
        headers: { Authorization: `Bearer ${t}` },
      });
      const u: AuthUser = { id: data.id, email: data.email, plan: data.plan, api_key: data.api_key, first_name: data.first_name ?? null, last_name: data.last_name ?? null, google_id: data.google_id ?? null, is_admin: data.is_admin ?? false, mfa_enabled: data.mfa_enabled ?? false };
      setUser(u);
      analyticsIdentify(u.id, u.email, u.plan);
    } catch {
      // Token invalide ou expiré — on efface l'état auth sans redirection
      // (window.location.href = '/' causerait un rechargement de page
      //  pendant un scan en cours pour les utilisateurs non-connectés)
      localStorage.removeItem('wezea_token');
      setToken(null);
      setUser(null);
      analyticsReset();
    }
  }

  async function login(email: string, password: string) {
    try {
      const { data } = await authApi.post('/auth/login', { email, password });
      // Si mfa_required, laisser LoginPage gérer la suite
      if (data.mfa_required) return;
      localStorage.setItem('wezea_token', data.access_token);
      setToken(data.access_token);
      const u: AuthUser = { ...data.user, first_name: data.user.first_name ?? null, last_name: data.user.last_name ?? null, is_admin: data.user.is_admin ?? false, mfa_enabled: data.user.mfa_enabled ?? false };
      setUser(u);
      analyticsIdentify(u.id, u.email, u.plan);
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Erreur de connexion';
      throw new Error(typeof msg === 'string' ? msg : 'Erreur de connexion');
    }
  }

  function loginWithToken(accessToken: string, userData: Partial<AuthUser>) {
    localStorage.setItem('wezea_token', accessToken);
    setToken(accessToken);
    const u: AuthUser = {
      id: userData.id ?? 0,
      email: userData.email ?? '',
      plan: (userData.plan as AuthUser['plan']) ?? 'free',
      api_key: userData.api_key ?? null,
      first_name: userData.first_name ?? null,
      last_name: userData.last_name ?? null,
      google_id: userData.google_id ?? null,
      is_admin: userData.is_admin ?? false,
      mfa_enabled: userData.mfa_enabled ?? false,
    };
    setUser(u);
    analyticsIdentify(u.id, u.email, u.plan);
  }

  async function register(email: string, password: string) {
    try {
      const { data } = await authApi.post('/auth/register', { email, password });
      localStorage.setItem('wezea_token', data.access_token);
      setToken(data.access_token);
      const u: AuthUser = { ...data.user, first_name: data.user.first_name ?? null, last_name: data.user.last_name ?? null, is_admin: data.user.is_admin ?? false, mfa_enabled: data.user.mfa_enabled ?? false };
      setUser(u);
      analyticsIdentify(u.id, u.email, u.plan);
    } catch (err: any) {
      const msg = err.response?.data?.detail || "Erreur lors de l'inscription";
      throw new Error(typeof msg === 'string' ? msg : "Erreur lors de l'inscription");
    }
  }

  function logout() {
    localStorage.removeItem('wezea_token');
    setToken(null);
    setUser(null);
    analyticsReset();
    window.location.href = '/';
  }

  function authHeaders(): Record<string, string> {
    return token ? { Authorization: `Bearer ${token}` } : {};
  }

  async function updateProfile(first_name: string | null, last_name: string | null) {
    if (!token) throw new Error('Non connecté');
    const { data } = await authApi.patch('/auth/profile', { first_name, last_name }, {
      headers: { Authorization: `Bearer ${token}` },
    });
    setUser(prev => prev ? { ...prev, first_name: data.first_name ?? null, last_name: data.last_name ?? null } : null);
  }

  async function googleLogin(idToken: string): Promise<{ mfa_required?: boolean; mfa_token?: string }> {
    const { data } = await authApi.post('/auth/google', { id_token: idToken });
    // Si le compte a la 2FA activée, retourner sans loguer — LoginPage gère la suite
    if (data.mfa_required) {
      return { mfa_required: true, mfa_token: data.mfa_token };
    }
    localStorage.setItem('wezea_token', data.access_token);
    setToken(data.access_token);
    const u: AuthUser = { ...data.user, first_name: data.user.first_name ?? null, last_name: data.user.last_name ?? null, google_id: data.user.google_id ?? null, is_admin: data.user.is_admin ?? false, mfa_enabled: data.user.mfa_enabled ?? false };
    setUser(u);
    analyticsIdentify(u.id, u.email, u.plan);
    return {};
  }

  async function upgradeToPlan(plan: 'starter' | 'pro' | 'dev'): Promise<string> {
    if (!token) throw new Error('Non connecté');
    const { data } = await authApi.post('/payment/create-checkout', { plan }, {
      headers: { Authorization: `Bearer ${token}` },
    });
    return data.checkout_url as string;
  }

  async function getPortalUrl(): Promise<string> {
    if (!token) throw new Error('Non connecté');
    const { data } = await authApi.get('/payment/portal', {
      headers: { Authorization: `Bearer ${token}` },
    });
    return data.portal_url as string;
  }

  async function refreshUser(): Promise<void> {
    if (token) await fetchMe(token);
  }

  async function deleteAccount(password: string) {
    if (!token) throw new Error('Non connecté');
    await authApi.delete('/auth/account', {
      data: { password },
      headers: { Authorization: `Bearer ${token}` },
    });
    logout();
  }

  return (
    <AuthContext.Provider value={{ user, token, loading, login, loginWithToken, register, googleLogin, logout, authHeaders, updateProfile, deleteAccount, upgradeToPlan, getPortalUrl, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
