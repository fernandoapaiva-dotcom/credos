import React, { useEffect, useState } from 'react';
import { useAuth, api } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';
import { Building2, Plus, LogOut, Loader2, ArrowRight } from 'lucide-react';
import { useTheme } from '../context/ThemeContext';

interface Company {
  id: number;
  empresa_nome: string;
  empresa_cnpj: string;
  logo_b64?: string;
}

export const Companies: React.FC = () => {
  const { user, setCompany, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const navigate = useNavigate();
  
  const [companies, setCompanies] = useState<Company[]>([]);
  const [loading, setLoading] = useState(true);
  const [isAdding, setIsAdding] = useState(false);
  
  // Form para nova empresa
  const [nome, setNome] = useState('');
  const [cnpj, setCnpj] = useState('');
  const [addingLoading, setAddingLoading] = useState(false);
  const [error, setError] = useState('');

  const fetchCompanies = async () => {
    try {
      setLoading(true);
      const res = await api.get('/companies/');
      setCompanies(res.data.companies || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCompanies();
  }, []);

  const handleSelect = (cnpj: string) => {
    setCompany(cnpj);
    navigate('/dashboard');
  };

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!nome || !cnpj) return;
    setAddingLoading(true);
    setError('');
    
    try {
      await api.post('/companies/', { nome, cnpj });
      setIsAdding(false);
      setNome('');
      setCnpj('');
      fetchCompanies();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Erro ao criar empresa');
    } finally {
      setAddingLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-dark-bg flex flex-col items-center py-12 px-4 transition-colors">
      
      {/* HEADER */}
      <div className="w-full max-w-4xl flex items-center justify-between mb-8 animate-fade-in">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-primary-600 text-white flex justify-center items-center shadow-md">
            <span className="font-bold text-lg">{user?.nome_completo?.[0] || 'U'}</span>
          </div>
          <div>
            <h2 className="text-xl font-bold dark:text-white">Olá, {user?.nome_completo}</h2>
            <p className="text-sm text-slate-500 dark:text-slate-400">Selecione onde deseja trabalhar hoje</p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <button onClick={toggleTheme} className="p-2 rounded-full hover:bg-slate-200 dark:hover:bg-slate-800 transition-colors">
            {theme === 'dark' ? '☀️' : '🌙'}
          </button>
          <button onClick={() => { logout(); navigate('/login'); }} className="flex items-center gap-2 text-red-600 hover:text-red-700 font-medium text-sm">
            <LogOut size={16}/> Sair
          </button>
        </div>
      </div>

      {/* CONTENT */}
      <div className="w-full max-w-4xl">
        {loading ? (
          <div className="flex justify-center py-20">
            <Loader2 className="animate-spin text-primary-500" size={40} />
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 animate-slide-up">
            
            {companies.map((c) => (
              <div 
                key={c.id} 
                onClick={() => handleSelect(c.empresa_cnpj)}
                className="card flex flex-col items-center justify-center p-8 cursor-pointer hover:-translate-y-1 hover:shadow-lg transition-all border-b-4 border-b-transparent hover:border-b-primary-500 group"
              >
                {c.logo_b64 ? (
                  <img src={`data:image/png;base64,${c.logo_b64}`} className="w-16 h-16 rounded-full object-cover mb-4 shadow-sm" alt="Logo" />
                ) : (
                  <div className="w-16 h-16 rounded-full bg-slate-100 dark:bg-dark-bg text-slate-400 flex items-center justify-center mb-4 group-hover:text-primary-500 transition-colors">
                    <Building2 size={32} />
                  </div>
                )}
                <h3 className="font-bold text-lg text-slate-900 dark:text-white text-center">{c.empresa_nome}</h3>
                <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">CNPJ: {c.empresa_cnpj}</p>
                <div className="mt-4 opacity-0 group-hover:opacity-100 transition-opacity flex items-center text-primary-600 dark:text-primary-400 text-sm font-medium gap-1">
                  Acessar <ArrowRight size={16} />
                </div>
              </div>
            ))}

            {/* ADD NOVO */}
            {!isAdding ? (
              <div 
                onClick={() => setIsAdding(true)}
                className="border-2 border-dashed border-slate-300 dark:border-dark-border rounded-xl flex flex-col items-center justify-center p-8 cursor-pointer hover:border-primary-500 hover:bg-primary-50/50 dark:hover:bg-primary-900/10 transition-colors group h-full"
              >
                <div className="w-12 h-12 rounded-full bg-primary-100 text-primary-600 dark:bg-primary-900/40 dark:text-primary-400 flex justify-center items-center mb-4 group-hover:scale-110 transition-transform">
                  <Plus size={24} />
                </div>
                <h3 className="font-medium text-slate-700 dark:text-slate-300">Cadastrar Unidade</h3>
              </div>
            ) : (
              <div className="card shadow-lg ring-2 ring-primary-500/50 p-6 flex flex-col justify-center">
                <h3 className="font-bold text-slate-900 dark:text-white mb-4">Nova Empresa</h3>
                {error && <div className="text-red-500 text-xs mb-3">{error}</div>}
                <form onSubmit={handleAdd} className="space-y-3">
                  <input 
                    type="text" 
                    placeholder="Razão Social" 
                    required value={nome} onChange={e=>setNome(e.target.value)} 
                    className="input-field text-sm py-2" 
                  />
                  <input 
                    type="text" 
                    placeholder="CNPJ (Apenas números)" 
                    required value={cnpj} onChange={e=>setCnpj(e.target.value)} 
                    className="input-field text-sm py-2" 
                  />
                  <div className="flex gap-2 pt-2">
                    <button type="button" onClick={() => setIsAdding(false)} className="btn-secondary text-sm py-1.5 flex-1">Cancelar</button>
                    <button type="submit" disabled={addingLoading} className="btn-primary text-sm py-1.5 flex-1">Salvar</button>
                  </div>
                </form>
              </div>
            )}

          </div>
        )}
      </div>

    </div>
  );
};
