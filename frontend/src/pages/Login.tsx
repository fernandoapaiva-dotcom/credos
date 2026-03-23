import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';
import { Mail, Lock, KeyRound, ArrowLeft } from 'lucide-react';
import axios from 'axios';

export const Login: React.FC = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  
  const [isForgot, setIsForgot] = useState(false);
  const [forgotEmail, setForgotEmail] = useState('');
  const [forgotMsg, setForgotMsg] = useState('');

  const { login } = useAuth();
  const navigate = useNavigate();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res = await axios.post('/api/auth/login', { username, password });
      login(res.data.access_token, res.data.user);
      navigate('/companies');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Erro ao fazer login. Tente novamente.');
    } finally {
      setLoading(false);
    }
  };

  const handleForgot = async (e: React.FormEvent) => {
    e.preventDefault();
    setForgotMsg('');
    setError('');
    setLoading(true);
    try {
      const res = await axios.post('/api/auth/forgot-password', { email: forgotEmail });
      setForgotMsg(res.data.message);
    } catch (err: any) {
      setError('Erro ao solicitar redefinição.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-dark-bg p-4 transition-colors duration-300 relative overflow-hidden">
      
      {/* Background decoration */}
      <div className="absolute top-[-10%] left-[-10%] w-96 h-96 bg-primary-500/20 rounded-full blur-3xl pointer-events-none"></div>
      <div className="absolute bottom-[-10%] right-[-10%] w-96 h-96 bg-blue-600/20 rounded-full blur-3xl pointer-events-none"></div>

      <div className="glass-panel w-full max-w-md p-8 rounded-2xl relative z-10 animate-fade-in">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-white shadow-sm mb-4 dark:bg-slate-800">
            <img src="/logo.png" className="w-12 h-12 object-contain" alt="Credos" />
          </div>
          <h1 className="text-2xl font-black text-slate-900 dark:text-white mb-2">Credos</h1>
          <p className="text-slate-500 dark:text-slate-400">
            {isForgot ? 'Recuperação de conta' : 'Acesse sua conta para continuar'}
          </p>
        </div>

        {!isForgot ? (
          <form onSubmit={handleLogin} className="space-y-5 animate-slide-up">
            {error && <div className="p-3 bg-red-100 text-red-700 rounded-lg text-sm">{error}</div>}
            
            <div className="space-y-1">
              <label className="text-sm font-medium text-slate-700 dark:text-slate-300">Usuário</label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <Mail className="h-5 w-5 text-slate-400" />
                </div>
                <input
                  type="text"
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="input-field pl-10 block w-full"
                  placeholder="Seu email corporativo"
                />
              </div>
            </div>

            <div className="space-y-1">
              <label className="text-sm font-medium text-slate-700 dark:text-slate-300">Senha</label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <Lock className="h-5 w-5 text-slate-400" />
                </div>
                <input
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="input-field pl-10 block w-full"
                  placeholder="••••••••"
                />
              </div>
              <div className="flex justify-end pt-1">
                <button 
                  type="button" 
                  onClick={() => { setIsForgot(true); setError(''); }}
                  className="text-sm text-primary-600 hover:text-primary-700 dark:text-primary-400 font-medium"
                >
                  Esqueceu a senha?
                </button>
              </div>
            </div>

            <button type="submit" disabled={loading} className="btn-primary w-full py-2.5">
              {loading ? 'Entrando...' : 'Entrar na Plataforma'}
            </button>
          </form>
        ) : (
          <form onSubmit={handleForgot} className="space-y-5 animate-slide-up">
            {error && <div className="p-3 bg-red-100 text-red-700 rounded-lg text-sm">{error}</div>}
            {forgotMsg && <div className="p-3 bg-green-100 text-green-700 rounded-lg text-sm">{forgotMsg}</div>}
            
            <div className="space-y-1">
              <label className="text-sm font-medium text-slate-700 dark:text-slate-300">Email da Conta</label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <KeyRound className="h-5 w-5 text-slate-400" />
                </div>
                <input
                  type="email"
                  required
                  value={forgotEmail}
                  onChange={(e) => setForgotEmail(e.target.value)}
                  className="input-field pl-10 block w-full"
                  placeholder="joao@empresa.com"
                />
              </div>
              <p className="text-xs text-slate-500 pt-1">
                Enviaremos um link de recuperação para o seu email.
              </p>
            </div>

            <button type="submit" disabled={loading} className="btn-primary w-full py-2.5">
              {loading ? 'Enviando...' : 'Enviar Link de Recuperação'}
            </button>
            <button 
              type="button" 
              onClick={() => { setIsForgot(false); setForgotMsg(''); setError(''); }}
              className="w-full flex items-center justify-center gap-2 text-sm text-slate-600 hover:text-slate-800 dark:text-slate-400 mt-4"
            >
              <ArrowLeft size={16} /> Voltar para o Login
            </button>
          </form>
        )}
      </div>
    </div>
  );
};
