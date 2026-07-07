import React, { createContext, useContext, useEffect, useState } from 'react';

import { loadToken, setToken } from './api';

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

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setTokenState] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    loadToken().then((t) => {
      setTokenState(t);
      setReady(true);
    });
  }, []);

  const signIn = async (t: string) => {
    await setToken(t);
    setTokenState(t);
  };

  const signOut = async () => {
    await setToken(null);
    setTokenState(null);
  };

  return (
    <AuthContext.Provider value={{ token, ready, signIn, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
