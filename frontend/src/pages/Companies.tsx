import React, { useEffect, useState } from 'react';
import { useAuth, api } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';
import { Building2, Plus, LogOut, Loader2, ArrowRight, Edit2, Trash2, X } from 'lucide-react';
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

  // Edit State
  const [isEditing, setIsEditing] = useState(false);
  const [editingCompany, setEditingCompany] = useState<Company | null>(null);
  const [editNome, setEditNome] = useState('');
  const [editCnpj, setEditCnpj] = useState('');
  const [editEmail, setEditEmail] = useState('');
  const [editWaInstance, setEditWaInstance] = useState('');
  const [configLoading, setConfigLoading] = useState(false);

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

  // Seleção automática se houver apenas uma empresa (Otimização para SSO/Hub)
  useEffect(() => {
    if (!loading && companies.length === 1 && !isAdding && !isEditing) {
      const singleCompany = companies[0];
      console.log(`Auto-selecionando empresa única: ${singleCompany.empresa_nome}`);
      handleSelect(singleCompany.empresa_cnpj);
    }
  }, [loading, companies, isAdding, isEditing]);

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

  const handleEditInit = async (e: React.MouseEvent, company: Company) => {
    e.stopPropagation();
    setEditingCompany(company);
    setEditNome(company.empresa_nome);
    setEditCnpj(company.empresa_cnpj);
    setIsEditing(true);
    setError('');

    // Busca as configs para preencher os campos de email/wa
    try {
      setConfigLoading(true);
      const res = await api.get(`/companies/${company.empresa_cnpj}/config`);
      setEditEmail(res.data.fin_mail_user || '');
      setEditWaInstance(res.data.instance_name || company.empresa_cnpj);
    } catch (err) {
      console.error("Erro ao buscar configs da empresa", err);
    } finally {
      setConfigLoading(false);
    }
  };

  const handleUpdate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingCompany || !editNome || !editCnpj) return;
    setAddingLoading(true);
    setError('');
    
    try {
      // 1. Atualiza dados centrais (Nome/CNPJ)
      await api.put(`/companies/${editingCompany.empresa_cnpj}`, { 
        nome: editNome, 
        cnpj: editCnpj 
      });

      // 2. Atualiza configs específicas (Email/WhatsApp)
      // Usamos o novo CNPJ se ele mudou, ou o antigo
      const targetCnpj = editCnpj;
      await api.patch(`/companies/${targetCnpj}/config`, {
        fin_mail_user: editEmail,
        // O campo no banco é 'empresa_cnpj' mas às vezes o user quer um alias
      });

      setIsEditing(false);
      fetchCompanies();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Erro ao atualizar empresa');
    } finally {
      setAddingLoading(false);
    }
  };

  const handleDelete = async (e: React.MouseEvent, cnpj: string) => {
    e.stopPropagation();
    if (!window.confirm('Tem certeza que deseja excluir esta empresa e todos os seus dados? Esta ação é irreversível.')) return;
    
    try {
      await api.delete(`/companies/${cnpj}`);
      fetchCompanies();
    } catch (err) {
      console.error(err);
      alert('Erro ao excluir empresa');
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
                className="card relative flex flex-col items-center justify-center p-8 cursor-pointer hover:-translate-y-1 hover:shadow-lg transition-all border-b-4 border-b-transparent hover:border-b-primary-500 group"
              >
                {/* AÇÕES */}
                <div className="absolute top-3 right-3 flex gap-1 z-10">
                  <button 
                    onClick={(e) => handleEditInit(e, c)}
                    className="p-2 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:text-primary-600 dark:hover:text-primary-400 shadow-sm border border-slate-200 dark:border-slate-700 transition-colors"
                    title="Editar"
                  >
                    <Edit2 size={16} />
                  </button>
                  <button 
                    onClick={(e) => handleDelete(e, c.empresa_cnpj)}
                    className="p-2 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:text-red-600 shadow-sm border border-slate-200 dark:border-slate-700 transition-colors"
                    title="Excluir"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>

                <div className="w-20 h-20 rounded-xl bg-white flex items-center justify-center p-2 mb-4 shadow-md group-hover:scale-105 transition-transform overflow-hidden">
                  {c.logo_b64 ? (
                    <img src={c.logo_b64} className="max-w-full max-h-full object-contain" alt="Logo" />
                  ) : (
                    <Building2 size={32} className="text-slate-300" />
                  )}
                </div>
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

      {/* MODAL EDITAR */}
      {isEditing && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="card w-full max-w-md p-6 shadow-2xl animate-fade-in">
            <div className="flex justify-between items-center mb-6">
              <h3 className="text-xl font-bold dark:text-white">Editar Empresa</h3>
              <button onClick={() => setIsEditing(false)} className="p-1 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg">
                <X size={20} />
              </button>
            </div>

            {error && <div className="p-3 bg-red-50 text-red-600 rounded-lg text-sm mb-4">{error}</div>}

            <form onSubmit={handleUpdate} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1 px-1">Razão Social</label>
                <input 
                  type="text" 
                  required 
                  value={editNome} 
                  onChange={e=>setEditNome(e.target.value)} 
                  className="input-field"
                  placeholder="Ex: Empresa de Exemplo LTDA"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1 px-1">CNPJ (Apenas números)</label>
                <input 
                  type="text" 
                  required 
                  value={editCnpj} 
                  onChange={e=>setEditCnpj(e.target.value)} 
                  className="input-field"
                  placeholder="Ex: 00000000000191"
                />
                <p className="text-[10px] text-amber-600 dark:text-amber-500 mt-1 px-1">⚠️ Alterar o CNPJ moverá todos os dados do banco antigo para o novo.</p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1 px-1">E-mail de Envio</label>
                  <input 
                    type="email" 
                    value={editEmail} 
                    onChange={e=>setEditEmail(e.target.value)} 
                    className="input-field"
                    placeholder="financeiro@empresa.com"
                    disabled={configLoading}
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1 px-1">Instância WhatsApp</label>
                  <input 
                    type="text" 
                    value={editWaInstance} 
                    className="input-field bg-slate-50 dark:bg-slate-800 opacity-60 cursor-not-allowed"
                    placeholder="Mesmo que o CNPJ"
                    disabled={true}
                  />
                  <p className="text-[10px] text-slate-400 mt-1 px-1">Automático (vinculado ao CNPJ)</p>
                </div>
              </div>

              <div className="flex gap-3 pt-4">
                <button type="button" onClick={() => setIsEditing(false)} className="btn-secondary flex-1 py-2.5">
                  Cancelar
                </button>
                <button type="submit" disabled={addingLoading} className="btn-primary flex-1 py-2.5">
                  {addingLoading ? <Loader2 className="animate-spin" size={18} /> : 'Salvar Alterações'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

    </div>
  );
};
