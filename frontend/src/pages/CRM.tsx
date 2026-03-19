import React, { useEffect, useState } from 'react';
import { Layout } from '../components/ui/Layout';
import { api } from '../context/AuthContext';
import { Search, Edit2, CheckCircle2, AlertCircle, XCircle, Clock, Trash2, ArrowRight } from 'lucide-react';

interface Client {
  id: number;
  nome: string;
  cnpj: string;
  whatsapp: string;
  email: string;
  contato: string;
}

interface Title {
  id: number;
  pagador: string;
  numero_nf: string;
  vencimento: string;
  valor: number;
  status: string;
  acao: string;
}

export const CRM: React.FC = () => {
  const [clients, setClients] = useState<Client[]>([]);
  const [filter, setFilter] = useState('');
  const [selectedClient, setSelectedClient] = useState<Client | null>(null);
  const [titles, setTitles] = useState<Title[]>([]);
  
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchClients();
  }, []);

  const fetchClients = async () => {
    setLoading(true);
    try {
      const res = await api.get('/crm/clients');
      setClients(res.data.clients || []);
    } catch(e) { }
    setLoading(false);
  };

  const fetchTitles = async (nome: string) => {
    try {
      const res = await api.get(`/crm/clients/${nome}/titles`);
      setTitles(res.data.titles || []);
    } catch(e) { }
  };

  const handleSelectClient = (c: Client) => {
    setSelectedClient(c);
    fetchTitles(c.nome);
  };

  const updateTitleStatus = async (id: number, newStatus: string, action: string) => {
    try {
      await api.patch(`/crm/titles/${id}`, { status: newStatus, acao: action });
      if (selectedClient) fetchTitles(selectedClient.nome);
    } catch(e) {
      alert("Erro ao atualizar.");
    }
  };

  const filteredClients = clients.filter(c => 
    c.nome.toLowerCase().includes(filter.toLowerCase()) || 
    c.cnpj.includes(filter)
  );

  const getStatusColor = (status: string) => {
    switch(status) {
      case 'Aberto': return 'bg-blue-100 text-blue-800 border-blue-200 dark:bg-blue-900/30 dark:text-blue-400 dark:border-blue-800';
      case 'Pago': return 'bg-green-100 text-green-800 border-green-200 dark:bg-green-900/30 dark:text-green-400 dark:border-green-800';
      case 'Negociado': return 'bg-amber-100 text-amber-800 border-amber-200 dark:bg-amber-900/30 dark:text-amber-400 dark:border-amber-800';
      case 'Cartório': return 'bg-red-100 text-red-800 border-red-200 dark:bg-red-900/30 dark:text-red-400 dark:border-red-800';
      default: return 'bg-slate-100 text-slate-800 border-slate-200 dark:bg-slate-800 py-1 dark:text-slate-300 dark:border-slate-700';
    }
  };

  return (
    <Layout title="CRM e Carteira">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-full">
        
        {/* CLIENTS LIST */}
        <div className="card h-[calc(100vh-8rem)] flex flex-col p-4 col-span-1">
          <div className="mb-4">
            <h3 className="font-bold text-lg mb-2 dark:text-white">Clientes</h3>
            <div className="relative">
              <Search className="absolute left-3 top-2.5 text-slate-400" size={18} />
              <input 
                type="text" 
                placeholder="Buscar por nome ou CNPJ..." 
                className="input-field pl-9"
                value={filter}
                onChange={e => setFilter(e.target.value)}
              />
            </div>
          </div>
          
          <div className="flex-1 overflow-y-auto pr-2 space-y-2">
            {filteredClients.map(c => (
              <div 
                key={c.id} 
                onClick={() => handleSelectClient(c)}
                className={`p-3 rounded-lg border cursor-pointer transition-colors ${selectedClient?.id === c.id ? 'bg-primary-50 border-primary-300 dark:bg-primary-900/20 dark:border-primary-700' : 'bg-white border-slate-200 hover:bg-slate-50 dark:bg-dark-surface dark:border-dark-border dark:hover:bg-dark-bg/50'}`}
              >
                <div className="font-medium text-slate-900 dark:text-white truncate">{c.nome}</div>
                <div className="text-xs text-slate-500 dark:text-slate-400">{c.cnpj}</div>
              </div>
            ))}
          </div>
        </div>

        {/* TITLES AREA */}
        <div className="card col-span-2 h-[calc(100vh-8rem)] flex flex-col p-0 overflow-hidden">
          {selectedClient ? (
            <>
              <div className="p-6 border-b border-slate-200 dark:border-dark-border bg-slate-50/50 dark:bg-dark-surface/50">
                <h2 className="text-xl font-bold dark:text-white">{selectedClient.nome}</h2>
                <div className="flex space-x-4 mt-2 text-sm text-slate-600 dark:text-slate-400">
                  <span><strong className="font-medium">CNPJ:</strong> {selectedClient.cnpj}</span>
                  <span><strong className="font-medium">WhatsApp:</strong> {selectedClient.whatsapp}</span>
                </div>
              </div>
              
              <div className="flex-1 overflow-y-auto p-6">
                <h3 className="font-bold mb-4 dark:text-white flex items-center gap-2">Títulos <span className="px-2 py-0.5 bg-primary-100 text-primary-700 dark:bg-primary-900/30 dark:text-primary-400 rounded-full text-xs">{titles.length}</span></h3>
                
                {titles.length === 0 ? (
                  <div className="text-center py-10 text-slate-500">Nenhum título encontrado para este cliente.</div>
                ) : (
                  <div className="space-y-4">
                    {titles.map(t => (
                      <div key={t.id} className="border border-slate-200 dark:border-dark-border rounded-xl p-4 flex flex-col sm:flex-row items-center justify-between gap-4 bg-white dark:bg-dark-surface">
                        <div className="flex-1">
                          <div className="flex items-center gap-3 mb-1">
                            <span className="font-bold text-lg dark:text-white">R$ {t.valor.toLocaleString('pt-BR', {minimumFractionDigits: 2})}</span>
                            <span className={`px-2.5 py-0.5 text-xs font-semibold rounded-full border ${getStatusColor(t.status)}`}>
                              {t.status}
                            </span>
                          </div>
                          <div className="text-sm text-slate-500 dark:text-slate-400 flex flex-wrap gap-4 items-center mt-1">
                            <span>NF: {t.numero_nf}</span>
                            <span>Venc: {t.vencimento}</span>
                            
                            <div className="flex items-center gap-2">
                              <label className="text-xs font-semibold">Status:</label>
                              <select 
                                value={t.status}
                                onChange={(e) => updateTitleStatus(t.id, e.target.value, t.acao)}
                                className="text-xs border border-slate-300 dark:border-dark-border rounded px-2 py-1 bg-white dark:bg-dark-surface dark:text-white"
                              >
                                <option value="Aberto">Aberto</option>
                                <option value="Pago">Pago</option>
                                <option value="Negociado">Negociado</option>
                                <option value="Cartório">Cartório</option>
                                <option value="Baixado">Baixado</option>
                                <option value="Cancelado">Cancelado</option>
                              </select>
                            </div>

                            <div className="flex items-center gap-2">
                              <label className="text-xs font-semibold">Ação:</label>
                              <select 
                                value={t.acao}
                                onChange={(e) => updateTitleStatus(t.id, t.status, e.target.value)}
                                className="text-xs border border-slate-300 dark:border-dark-border rounded px-2 py-1 bg-white dark:bg-dark-surface dark:text-white"
                              >
                                <option value="Cobrar">Cobrar</option>
                                <option value="Pausar">Pausar</option>
                              </select>
                            </div>
                          </div>
                        </div>
                        
                        {/* Ações Inteligentes Baseadas em Status */}
                        <div className="flex items-center gap-2 flex-wrap sm:flex-nowrap justify-end">
                          {t.status === 'Aberto' && (
                            <>
                              <button onClick={() => updateTitleStatus(t.id, 'Aberto', 'Cobrar')} className="btn-secondary text-xs px-3 py-1.5"><Clock size={14} className="mr-1"/> Cobrar</button>
                              <button onClick={() => updateTitleStatus(t.id, 'Pago', 'Pausar')} className="btn-primary bg-green-600 hover:bg-green-700 ring-green-600 text-xs px-3 py-1.5"><CheckCircle2 size={14} className="mr-1"/> Marcar Pago</button>
                              <button onClick={() => updateTitleStatus(t.id, 'Negociado', 'Pausar')} className="btn-secondary text-xs px-3 py-1.5">Negociar</button>
                            </>
                          )}
                          
                          {t.status === 'Pago' && (
                            <button onClick={() => updateTitleStatus(t.id, 'Baixado', 'Pausar')} className="btn-secondary text-xs px-3 py-1.5"><Trash2 size={14} className="mr-1"/> Mover p/ Baixados</button>
                          )}

                          {t.status === 'Negociado' && (
                            <>
                              <button onClick={() => updateTitleStatus(t.id, 'Pago', 'Pausar')} className="btn-primary bg-green-600 hover:bg-green-700 text-xs px-3 py-1.5"><CheckCircle2 size={14} className="mr-1"/> Recebido</button>
                              <button onClick={() => updateTitleStatus(t.id, 'Aberto', 'Cobrar')} className="btn-secondary text-xs px-3 py-1.5"><AlertCircle size={14} className="mr-1"/> Não Pago (Cobrar Novamente)</button>
                            </>
                          )}

                          {t.status === 'Cartório' && (
                            <button onClick={() => updateTitleStatus(t.id, 'Pago', 'Pausar')} className="btn-primary bg-green-600 hover:bg-green-700 text-xs px-3 py-1.5"><CheckCircle2 size={14} className="mr-1"/> Honorários Pagos</button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-slate-400 dark:text-slate-500">
              <Search size={48} className="mb-4 opacity-50" />
              <p>Selecione um cliente ao lado para ver seus títulos</p>
            </div>
          )}
        </div>

      </div>
    </Layout>
  );
};
