import React, { useState, useEffect } from 'react';
import { Layout } from '../components/ui/Layout';
import { api } from '../context/AuthContext';
import { UserPlus, Trash2, Shield, User as UserIcon, Loader2, Mail } from 'lucide-react';

interface User {
  login: string;
  nome_completo: string;
  perfil: string;
  status: string;
}

export const Users: React.FC = () => {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [newUser, setNewUser] = useState({ login: '', password: '', nome_completo: '', perfil: 'operador' });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchUsers();
  }, []);

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const res = await api.get('/users');
      setUsers(res.data.users);
    } catch (e) {
      console.error('Erro ao buscar usuários', e);
    } finally {
      setLoading(false);
    }
  };

  const handleAddUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.post('/users', newUser);
      setShowModal(false);
      setNewUser({ login: '', password: '', nome_completo: '', perfil: 'operador' });
      fetchUsers();
    } catch (e: any) {
      alert(e.response?.data?.detail || 'Erro ao criar usuário');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteUser = async (login: string) => {
    if (!window.confirm(`Tem certeza que deseja excluir o usuário ${login}?`)) return;
    try {
      await api.delete(`/users/${login}`);
      fetchUsers();
    } catch (e: any) {
      alert(e.response?.data?.detail || 'Erro ao excluir usuário');
    }
  };

  return (
    <Layout title="Gestão de Usuários">
      <div className="max-w-6xl mx-auto space-y-6">
        
        <div className="flex justify-between items-center">
          <div>
            <h2 className="text-xl font-bold dark:text-white">Usuários do Sistema</h2>
            <p className="text-sm text-slate-500">Gerencie quem tem acesso à plataforma Credos.</p>
          </div>
          <button 
            onClick={() => setShowModal(true)}
            className="btn-primary"
          >
            <UserPlus size={18} className="mr-2" /> Novo Usuário
          </button>
        </div>

        <div className="card overflow-hidden">
          {loading ? (
            <div className="p-12 flex justify-center">
              <Loader2 className="animate-spin text-primary-500" size={32} />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="bg-slate-50 dark:bg-dark-surface border-b border-slate-200 dark:border-dark-border">
                    <th className="px-6 py-4 text-xs font-bold uppercase tracking-wider text-slate-500">Usuário</th>
                    <th className="px-6 py-4 text-xs font-bold uppercase tracking-wider text-slate-500">Nome Completo</th>
                    <th className="px-6 py-4 text-xs font-bold uppercase tracking-wider text-slate-500">Perfil</th>
                    <th className="px-6 py-4 text-xs font-bold uppercase tracking-wider text-slate-500">Status</th>
                    <th className="px-6 py-4 text-xs font-bold uppercase tracking-wider text-slate-500 text-right">Ações</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-dark-border">
                  {users.map((u) => (
                    <tr key={u.login} className="hover:bg-slate-50/50 dark:hover:bg-dark-bg/30 transition-colors">
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-full bg-primary-100 flex items-center justify-center text-primary-600">
                             <Mail size={14} />
                          </div>
                          <span className="font-medium text-slate-700 dark:text-slate-300">{u.login}</span>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-slate-600 dark:text-slate-400">{u.nome_completo}</td>
                      <td className="px-6 py-4">
                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                          u.perfil === 'admin' 
                            ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400' 
                            : 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400'
                        }`}>
                          {u.perfil === 'admin' ? <Shield size={12} className="mr-1"/> : <UserIcon size={12} className="mr-1"/>}
                          {u.perfil}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                         <span className="text-xs text-green-600 font-bold bg-green-50 px-2 py-1 rounded">Ativo</span>
                      </td>
                      <td className="px-6 py-4 text-right">
                        <button 
                          onClick={() => handleDeleteUser(u.login)}
                          disabled={u.login === 'admin@credos.com' || u.login === 'fernando'}
                          className="p-2 text-slate-400 hover:text-red-600 disabled:opacity-30 disabled:hover:text-slate-400 transition-colors"
                        >
                          <Trash2 size={18} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {users.length === 0 && !loading && (
                <div className="p-12 text-center text-slate-400">Nenhum usuário cadastrado além do mestre.</div>
              )}
            </div>
          )}
        </div>

        {/* Modal Novo Usuário */}
        {showModal && (
          <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white dark:bg-dark-surface w-full max-w-md rounded-2xl shadow-2xl overflow-hidden animate-slide-up">
              <div className="p-6 border-b border-slate-100 dark:border-dark-border">
                <h3 className="text-xl font-bold dark:text-white">Cadastrar Novo Usuário</h3>
              </div>
              <form onSubmit={handleAddUser} className="p-6 space-y-4">
                <div>
                  <label className="block text-sm font-medium mb-1">Email / Login</label>
                  <input 
                    type="email" required className="input-field" 
                    value={newUser.login} onChange={e => setNewUser({...newUser, login: e.target.value})}
                    placeholder="ex: joao@empresa.com"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">Nome Completo</label>
                  <input 
                    type="text" required className="input-field" 
                    value={newUser.nome_completo} onChange={e => setNewUser({...newUser, nome_completo: e.target.value})}
                    placeholder="João Silva"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">Senha Provisória</label>
                  <input 
                    type="password" required className="input-field" 
                    value={newUser.password} onChange={e => setNewUser({...newUser, password: e.target.value})}
                    placeholder="••••••••"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">Perfil</label>
                  <select 
                    className="input-field" 
                    value={newUser.perfil} onChange={e => setNewUser({...newUser, perfil: e.target.value})}
                  >
                    <option value="operador">Operador (CRM & Relatórios)</option>
                    <option value="admin">Administrador (Acesso total)</option>
                  </select>
                </div>

                <div className="flex gap-3 pt-4">
                  <button type="button" onClick={() => setShowModal(false)} className="btn-secondary flex-1">Cancelar</button>
                  <button type="submit" disabled={saving} className="btn-primary flex-1">
                    {saving ? <Loader2 className="animate-spin mr-2" size={18}/> : <UserPlus size={18} className="mr-2"/>}
                    Criar Conta
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    </Layout>
  );
};
