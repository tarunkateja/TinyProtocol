import { useQueryClient } from '@tanstack/react-query';
import React, { createContext, useContext, useEffect, useState } from 'react';

import { api, loadToken, setToken, setUnauthorizedHandler, tokenIssuedAt } from './api';
import { showAlert } from './dialogs';

interface AuthState {
  token: string | null;
  ready: boolean;
  signIn: (token: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthState>({
  token: null,
  ready: false,
  signIn: async () => {},
  signOut: async () => {},
});

// Tokens last 90 days; trading in a day-old one on launch means a session
// only ends after 90 days of not opening the app.
const REFRESH_AFTER_S = 24 * 3600;

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const qc = useQueryClient();
  const [token, setTokenState] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  const signIn = async (t: string) => {
    await setToken(t);
    setTokenState(t);
  };

  const signOut = async () => {
    await setToken(null);
    setTokenState(null);
    qc.clear();
  };

  useEffect(() => {
    loadToken().then((t) => {
      setTokenState(t);
      setReady(true);
      const iat = t ? tokenIssuedAt(t) : null;
      if (t && (iat == null || Date.now() / 1000 - iat > REFRESH_AFTER_S)) {
        // A 401 here goes through the unauthorized handler below.
        api.refreshToken().then((r) => setToken(r.access_token)).catch(() => {});
      }
    });
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      signOut();
      showAlert('Please sign in again', 'Your session expired.');
    });
    return () => setUnauthorizedHandler(null);
  }, []);

  return (
    <AuthContext.Provider value={{ token, ready, signIn, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
