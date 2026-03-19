import React, { createContext, useContext, useState, useEffect } from 'react';
import axios from 'axios';

interface User {
  username: string;
  nome_completo: string;
  perfil: string;
  foto_b64?: string;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  companyCnpj: string | null;
  login: (token: string, user: User) => void;
  logout: () => void;
  setCompany: (cnpj: string) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

// API Client global para injetar token e company
export const api = axios.create({
  baseURL: '/api'
});

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(() => {
    const s = localStorage.getItem('user');
    return s ? JSON.parse(s) : null;
  });
  
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('token'));
  
  const [companyCnpj, setCompanyCnpj] = useState<string | null>(() => localStorage.getItem('companyCnpj'));

  useEffect(() => {
    if (token) {
      api.defaults.headers.common['Authorization'] = `Bearer ${token}`;
    } else {
      delete api.defaults.headers.common['Authorization'];
    }
    
    if (companyCnpj) {
      api.defaults.headers.common['x-company-cnpj'] = companyCnpj;
    } else {
      delete api.defaults.headers.common['x-company-cnpj'];
    }
  }, [token, companyCnpj]);

  const login = (newToken: string, newUser: User) => {
    setToken(newToken);
    setUser(newUser);
    localStorage.setItem('token', newToken);
    localStorage.setItem('user', JSON.stringify(newUser));
  };

  const logout = () => {
    setToken(null);
    setUser(null);
    setCompanyCnpj(null);
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    localStorage.removeItem('companyCnpj');
  };

  const setCompany = (cnpj: string) => {
    setCompanyCnpj(cnpj);
    localStorage.setItem('companyCnpj', cnpj);
  };

  return (
    <AuthContext.Provider value={{ user, token, companyCnpj, login, logout, setCompany }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider');
  return context;
};
