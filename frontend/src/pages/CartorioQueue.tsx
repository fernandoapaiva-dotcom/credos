import React, { useState, useEffect } from 'react';
import { Layout } from '../components/ui/Layout';
import { useAuth } from '../context/AuthContext';
import { api } from '../context/AuthContext';
import { Landmark, RefreshCw, AlertCircle, CheckCircle2, Clock, Search, Edit, X } from 'lucide-react';
import clsx from 'clsx';

interface CartorioJob {
  id: number;
  titulo_id: number;
  status_automacao: string;
  data_execucao: string;
  log_erro: string | null;
  numero_nf: string;
  pagador: string;
  valor: number;
}

export const CartorioQueue: React.FC = () => {
  const { companyCnpj } = useAuth();
  const [jobs, setJobs] = useState<CartorioJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [activeTab, setActiveTab] = useState<'fila' | 'historico'>('fila');
  
  // Modal Edit State
  const [editingJob, setEditingJob] = useState<any>(null);
  const [editForm, setEditForm] = useState({ emissao: '', vencimento: '', numero_nf: '', valor: 0 });

  const fetchJobs = async () => {
    if (!companyCnpj) return;
    setLoading(true);
    try {
      const res = await api.get(`/cartorio/status/${companyCnpj}`);
      setJobs(res.data || []);
    } catch (error) {
      console.error('Erro ao buscar fila do cartório:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchJobs();
    const interval = setInterval(fetchJobs, 10000); // refresh every 10s
    return () => clearInterval(interval);
  }, [companyCnpj]);

  const handleFileUpload = async (jobId: number, e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !companyCnpj) return;
    
    const formData = new FormData();
    formData.append('file', file);
    
    setLoading(true);
    try {
      await api.post(`/cartorio/status/${companyCnpj}/${jobId}/upload-nf`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      alert('Arquivo processado com sucesso! A data de emissão foi extraída e o título retornou para a fila de envio.');
      fetchJobs();
    } catch (error: any) {
      alert('Erro ao processar o arquivo: ' + (error.response?.data?.detail || error.message));
    } finally {
      setLoading(false);
      e.target.value = ''; // Reset input
    }
  };

  const handleOpenEdit = (job: any) => {
    setEditForm({
      emissao: job.emissao || '',
      vencimento: job.vencimento || '',
      numero_nf: job.numero_nf || '',
      valor: job.valor || 0
    });
    setEditingJob(job);
  };

  const handleSaveEdit = async () => {
    if (!companyCnpj || !editingJob) return;
    setLoading(true);
    try {
      await api.put(`/cartorio/titulo/${editingJob.titulo_id}`, editForm, {
        headers: { 'x-company-cnpj': companyCnpj }
      });
      alert('Dados salvos com sucesso! O título voltou para a fila.');
      setEditingJob(null);
      fetchJobs();
    } catch (error: any) {
      alert('Erro ao salvar dados: ' + (error.response?.data?.detail || error.message));
    } finally {
      setLoading(false);
    }
  };

  const handleResetJob = async (jobId: number) => {
    if (!companyCnpj) return;
    
    if (!window.confirm('Tem certeza que deseja enviar este título de volta para a fila?')) {
      return;
    }
    
    setLoading(true);
    try {
      await api.post(`/cartorio/status/${companyCnpj}/${jobId}/reset`);
      fetchJobs();
    } catch (error: any) {
      alert('Erro ao reprocessar: ' + (error.response?.data?.detail || error.message));
    } finally {
      setLoading(false);
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'Sucesso': return <CheckCircle2 className="w-5 h-5 text-green-500" />;
      case 'Processando': return <RefreshCw className="w-5 h-5 text-blue-500 animate-spin" />;
      case 'Pendente': return <Clock className="w-5 h-5 text-yellow-500" />;
      default: return <AlertCircle className="w-5 h-5 text-red-500" />;
    }
  };

  const filteredJobs = jobs.filter(job => {
    const term = searchTerm.toLowerCase();
    const matchesSearch = 
      (job.pagador || '').toLowerCase().includes(term) ||
      (job.numero_nf || '').toLowerCase().includes(term) ||
      (job.valor || '').toString().includes(term);

    const isFila = job.status_automacao === 'Pendente' || job.status_automacao === 'Processando';
    const matchesTab = activeTab === 'fila' ? isFila : !isFila;

    return matchesSearch && matchesTab;
  });

  return (
    <Layout title="Fila do Cartório">
      <div className="bg-white dark:bg-dark-surface rounded-xl shadow-sm border border-slate-200 dark:border-dark-border overflow-hidden">
        <div className="p-6 border-b border-slate-200 dark:border-dark-border flex flex-col md:flex-row md:items-center justify-between gap-4 bg-slate-50/50 dark:bg-dark-surface/50">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 rounded-lg">
              <Landmark size={24} />
            </div>
            <div>
              <h2 className="text-lg font-bold text-slate-800 dark:text-white">Gerenciamento de Protestos</h2>
              <p className="text-sm text-slate-500 dark:text-slate-400">Acompanhe a fila e o histórico de envios</p>
            </div>
          </div>
          <button 
            onClick={fetchJobs} 
            className="flex items-center gap-2 px-4 py-2 bg-white dark:bg-dark-bg border border-slate-200 dark:border-dark-border rounded-lg text-sm font-medium hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors text-slate-700 dark:text-slate-300 shadow-sm whitespace-nowrap"
          >
            <RefreshCw size={16} className={clsx(loading && "animate-spin")} />
            Atualizar
          </button>
        </div>

        <div className="p-4 border-b border-slate-200 dark:border-dark-border flex flex-col md:flex-row gap-4 items-center justify-between">
          <div className="flex bg-slate-100 dark:bg-dark-bg p-1 rounded-lg w-full md:w-auto">
            <button
              onClick={() => setActiveTab('fila')}
              className={clsx(
                "flex-1 md:flex-none px-6 py-2 rounded-md text-sm font-medium transition-all",
                activeTab === 'fila' ? "bg-white dark:bg-dark-surface text-blue-600 dark:text-blue-400 shadow-sm" : "text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300"
              )}
            >
              Fila Pendente
            </button>
            <button
              onClick={() => setActiveTab('historico')}
              className={clsx(
                "flex-1 md:flex-none px-6 py-2 rounded-md text-sm font-medium transition-all",
                activeTab === 'historico' ? "bg-white dark:bg-dark-surface text-blue-600 dark:text-blue-400 shadow-sm" : "text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300"
              )}
            >
              Histórico / Falhas
            </button>
          </div>

          <div className="relative w-full md:w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
            <input
              type="text"
              placeholder="Buscar cliente, NF ou valor..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-10 pr-4 py-2 bg-white dark:bg-dark-bg border border-slate-200 dark:border-dark-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 text-slate-700 dark:text-slate-300"
            />
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-50 dark:bg-dark-bg/50 text-slate-500 dark:text-slate-400 text-xs uppercase tracking-wider border-b border-slate-200 dark:border-dark-border">
                <th className="p-4 font-semibold">ID / Data</th>
                <th className="p-4 font-semibold">Cliente</th>
                <th className="p-4 font-semibold">Título</th>
                <th className="p-4 font-semibold">Status</th>
                <th className="p-4 font-semibold">Detalhes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-dark-border">
              {filteredJobs.length === 0 ? (
                <tr>
                  <td colSpan={5} className="p-8 text-center text-slate-500 dark:text-slate-400">
                    {loading ? 'Carregando...' : 'Nenhum registro encontrado nesta aba.'}
                  </td>
                </tr>
              ) : (
                filteredJobs.map((job) => (
                  <tr key={job.id} className="hover:bg-slate-50 dark:hover:bg-dark-bg/50 transition-colors">
                    <td className="p-4">
                      <div className="text-sm font-medium text-slate-900 dark:text-white">#{job.id}</div>
                      <div className="text-xs text-slate-500 dark:text-slate-400">{job.data_execucao || '-'}</div>
                    </td>
                    <td className="p-4 text-sm font-medium text-slate-800 dark:text-slate-200">
                      {job.pagador}
                    </td>
                    <td className="p-4">
                      <div className="text-sm font-medium text-slate-800 dark:text-slate-200">NF {job.numero_nf}</div>
                      <div className="text-xs text-slate-500 dark:text-slate-400">
                        R$ {Number(job.valor).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                      </div>
                    </td>
                    <td className="p-4">
                      <div className="flex items-center gap-2">
                        {getStatusIcon(job.status_automacao)}
                        <span className={clsx("text-sm font-medium", 
                          job.status_automacao === 'Sucesso' ? 'text-green-600 dark:text-green-400' :
                          job.status_automacao === 'Pendente' ? 'text-yellow-600 dark:text-yellow-400' :
                          job.status_automacao === 'Processando' ? 'text-blue-600 dark:text-blue-400' :
                          'text-red-600 dark:text-red-400'
                        )}>
                          {job.status_automacao}
                        </span>
                      </div>
                    </td>
                    <td className="p-4 text-sm max-w-xs">
                      {job.log_erro ? (
                        <div className="text-red-600 dark:text-red-400 font-medium mb-2 whitespace-normal break-words">
                          {job.log_erro}
                        </div>
                      ) : (
                        <div className="text-slate-600 dark:text-slate-400">-</div>
                      )}
                      
                      {job.status_automacao === 'Aguardando Dados' && (
                        <div className="mt-2">
                          <label className="cursor-pointer inline-flex items-center gap-1 px-3 py-1.5 bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 hover:bg-blue-100 dark:hover:bg-blue-800/50 rounded border border-blue-200 dark:border-blue-800 text-xs font-medium transition-colors">
                            <span>📄 Anexar PDF da NF</span>
                            <input 
                              type="file" 
                              accept=".pdf,.xml" 
                              className="hidden" 
                              onChange={(e) => handleFileUpload(job.id, e)}
                            />
                          </label>
                        </div>
                      )}
                      
                      {(job.status_automacao === 'Erro' || job.status_automacao === 'Sucesso') && (
                        <div className="mt-2 flex gap-2">
                          <button
                            onClick={() => handleResetJob(job.id)}
                            className="inline-flex items-center gap-1 px-3 py-1.5 bg-yellow-50 dark:bg-yellow-900/30 text-yellow-600 dark:text-yellow-400 hover:bg-yellow-100 dark:hover:bg-yellow-800/50 rounded border border-yellow-200 dark:border-yellow-800 text-xs font-medium transition-colors"
                          >
                            <RefreshCw size={14} />
                            Reprocessar
                          </button>
                          
                          <button
                            onClick={() => handleOpenEdit(job)}
                            className="inline-flex items-center gap-1 px-3 py-1.5 bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 rounded border border-slate-300 dark:border-slate-600 text-xs font-medium transition-colors"
                          >
                            <Edit size={14} />
                            Editar
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {editingJob && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white dark:bg-dark-surface rounded-xl shadow-xl border border-slate-200 dark:border-dark-border w-full max-w-md overflow-hidden">
            <div className="p-4 border-b border-slate-200 dark:border-dark-border flex justify-between items-center bg-slate-50 dark:bg-dark-bg/50">
              <h3 className="font-bold text-slate-800 dark:text-white flex items-center gap-2">
                <Edit size={18} className="text-blue-500" />
                Editar Dados do Título
              </h3>
              <button onClick={() => setEditingJob(null)} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200">
                <X size={20} />
              </button>
            </div>
            
            <div className="p-6 space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Número da NF</label>
                <input 
                  type="text" 
                  value={editForm.numero_nf} 
                  onChange={e => setEditForm({...editForm, numero_nf: e.target.value})}
                  className="w-full px-3 py-2 bg-white dark:bg-dark-bg border border-slate-300 dark:border-dark-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 text-slate-700 dark:text-slate-300"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Valor (R$)</label>
                <input 
                  type="number" step="0.01"
                  value={editForm.valor} 
                  onChange={e => setEditForm({...editForm, valor: parseFloat(e.target.value) || 0})}
                  className="w-full px-3 py-2 bg-white dark:bg-dark-bg border border-slate-300 dark:border-dark-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 text-slate-700 dark:text-slate-300"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Data Emissão</label>
                  <input 
                    type="date" 
                    value={editForm.emissao} 
                    onChange={e => setEditForm({...editForm, emissao: e.target.value})}
                    className="w-full px-3 py-2 bg-white dark:bg-dark-bg border border-slate-300 dark:border-dark-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 text-slate-700 dark:text-slate-300"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Data Vencimento</label>
                  <input 
                    type="date" 
                    value={editForm.vencimento} 
                    onChange={e => setEditForm({...editForm, vencimento: e.target.value})}
                    className="w-full px-3 py-2 bg-white dark:bg-dark-bg border border-slate-300 dark:border-dark-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 text-slate-700 dark:text-slate-300"
                  />
                </div>
              </div>
            </div>
            
            <div className="p-4 border-t border-slate-200 dark:border-dark-border bg-slate-50 dark:bg-dark-bg/50 flex justify-end gap-2">
              <button 
                onClick={() => setEditingJob(null)}
                className="px-4 py-2 bg-white dark:bg-dark-surface border border-slate-300 dark:border-dark-border rounded-lg text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
              >
                Cancelar
              </button>
              <button 
                onClick={handleSaveEdit}
                disabled={loading}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors shadow-sm disabled:opacity-50 flex items-center gap-2"
              >
                {loading && <RefreshCw size={14} className="animate-spin" />}
                Salvar e Reenviar
              </button>
            </div>
          </div>
        </div>
      )}
    </Layout>
  );
};
