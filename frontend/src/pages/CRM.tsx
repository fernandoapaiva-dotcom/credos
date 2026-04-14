import React, { useEffect, useState, useMemo } from 'react';
import { Layout } from '../components/ui/Layout';
import { api } from '../context/AuthContext';
import { Search, Edit2, CheckCircle2, AlertCircle, Clock, Trash2, Loader2, X, Send, FileWarning, Users, ChevronDown, Power, Sparkles, Building2, RefreshCw, FileText, FileDown, Eye } from 'lucide-react';

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
  data_envio_cartorio?: string;
  status_retorno_cartorio?: string;
}

export const CRM: React.FC = () => {
  const [clients, setClients] = useState<Client[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedClient, setSelectedClient] = useState<Client | null>(null);
  const [titles, setTitles] = useState<Title[]>([]);
  const [selectedTitleIds, setSelectedTitleIds] = useState<number[]>([]);
  
  const [activeTab, setActiveTab] = useState<'carteira' | 'comprovantes'>('carteira');
  const [titleFilter, setTitleFilter] = useState<'pendentes' | 'pagos' | 'cartorio'>('pendentes');
  const [vouchers, setVouchers] = useState<any[]>([]);
  const [loadingVouchers, setLoadingVouchers] = useState(false);
  const [loadingClients, setLoadingClients] = useState(false);
  const [loadingTitles, setLoadingTitles] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [selectedChannels, setSelectedChannels] = useState<'whatsapp' | 'email' | 'ambos'>('ambos');
  const [isChargingBulk, setIsChargingBulk] = useState(false);
  const [bulkProgress, setBulkProgress] = useState(0);
  const [bulkTotal, setBulkTotal] = useState(0);
  const [currentChargingName, setCurrentChargingName] = useState('');

  // Client Edit State
  const [isEditingClient, setIsEditingClient] = useState(false);
  const [editClientData, setEditClientData] = useState({
    nome: '',
    cnpj: '',
    email: '',
    whatsapp: '',
    contato: ''
  });
  const [editLoading, setEditLoading] = useState(false);
  
  // Charge Preview State
  const [isShowingPreview, setIsShowingPreview] = useState(false);
  const [previewData, setPreviewData] = useState<any[]>([]);
  const [expandedPreviewClients, setExpandedPreviewClients] = useState<string[]>([]);

  // AI Negotiation State
  const [isNegotiating, setIsNegotiating] = useState(false);
  const [showAiModal, setShowAiModal] = useState(false);
  const [aiProposal, setAiProposal] = useState({ cliente: '', proposta: '', total: 0 });
  const [sendingProposal, setSendingProposal] = useState(false);

  // Document Viewer State
  const [showDocsDrawer, setShowDocsDrawer] = useState(false);
  const [docsTitle, setDocsTitle]= useState<any>(null);
  const [docsLista, setDocsLista] = useState<any[]>([]);
  const [loadingDocs, setLoadingDocs] = useState(false);

  const companyCnpj = localStorage.getItem('companyCnpj') || '';

  const togglePreviewExpand = (name: string) => {
    setExpandedPreviewClients(prev => 
      prev.includes(name) ? prev.filter(n => n !== name) : [...prev, name]
    );
  };

  useEffect(() => {
    fetchClients();
    fetchVouchers();
  }, []);

  const fetchVouchers = async () => {
    if (!companyCnpj) return;
    setLoadingVouchers(true);
    try {
      const res = await api.get('/crm/vouchers');
      setVouchers(res.data.vouchers || []);
    } catch(e) { }
    setLoadingVouchers(false);
  };

  const handleProcessVoucher = async (id: number, acao: string) => {
    setActionLoading(true);
    try {
      await api.post(`/crm/vouchers/${id}/process?acao=${acao}`);
      fetchVouchers();
      if (selectedClient) fetchTitles(selectedClient.nome);
      alert('Processado com sucesso!');
    } catch(e) {
      alert('Erro ao processar comprovante.');
    }
    setActionLoading(false);
  };

  const fetchClients = async () => {
    if (!companyCnpj) return;
    setLoadingClients(true);
    try {
      const res = await api.get('/crm/clients');
      setClients(res.data.clients || []);
    } catch(e) {
      console.error("Erro ao buscar clientes", e);
    } finally {
      setLoadingClients(false);
    }
  };

  const fetchTitles = async (nome: string) => {
    if (!companyCnpj) return;
    setLoadingTitles(true);
    try {
      const res = await api.get(`/crm/clients/${nome}/titles`);
      setTitles(res.data.titles || []);
    } catch(e) {
      console.error("Erro ao buscar títulos", e);
    } finally {
      setLoadingTitles(false);
    }
  };

  const handleSelectClient = (c: Client) => {
    setSelectedClient(c);
    setSelectedTitleIds([]);
    fetchTitles(c.nome);
  };

  const updateTitleStatus = async (id: number, newStatus: string, action: string) => {
    setActionLoading(true);
    try {
      await api.patch(`/crm/titles/${id}`, { status: newStatus || 'Aberto', acao: action || 'Cobrar' });
      if (selectedClient) fetchTitles(selectedClient.nome);
    } catch(e: any) {
      console.error(e?.response?.data || e);
      alert("Erro ao atualizar status do título.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleBulkUpdateStatus = async (newStatus: string, action: string) => {
    if (selectedTitleIds.length === 0) return;
    const msg = newStatus === 'Pago' 
      ? `Deseja realmente marcar ${selectedTitleIds.length} títulos como PAGOS? Esta ação é irreversível e interromperá as cobranças.`
      : `Deseja mover ${selectedTitleIds.length} títulos para o status de ${newStatus}?`;

    if (!window.confirm(msg)) return;
    
    setActionLoading(true);
    try {
      await Promise.all(
        selectedTitleIds.map(id => api.patch(`/crm/titles/${id}`, { status: newStatus || 'Aberto', acao: action || 'Cobrar' }))
      );
      setSelectedTitleIds([]);
      if (selectedClient) fetchTitles(selectedClient.nome);
    } catch(e: any) {
      console.error(e?.response?.data || e);
      alert("Erro ao atualizar múltiplos títulos.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleChargeAll = async (silent = false) => {
    try {
      const res = await api.post('/crm/preview-charge-all');
      setPreviewData(res.data.preview || []);
      if (!silent) setIsShowingPreview(true);
    } catch(e) {
      if (!silent) alert("Erro ao gerar prévia de cobrança.");
    } finally {
      // Finalizado
    }
  };

  const confirmChargeAll = async () => {
    if (previewData.length === 0) return;
    setIsShowingPreview(false);
    setIsChargingBulk(true);
    setBulkTotal(previewData.length);
    setBulkProgress(0);
    
    let successCount = 0;
    let failCount = 0;

    for (let i = 0; i < previewData.length; i++) {
      const client = previewData[i];
      setCurrentChargingName(client.cliente);
      try {
        const canaisArray = selectedChannels === 'ambos' ? ['whatsapp', 'email'] : [selectedChannels];
        await api.post(`/crm/clients/${client.cliente}/charge`, { canais: canaisArray });
        successCount++;
      } catch (e) {
        console.error(`Erro ao cobrar ${client.cliente}`, e);
        failCount++;
      }
      setBulkProgress(i + 1);
    }

    setIsChargingBulk(false);
    alert(`Processo concluído!\nSucesso: ${successCount}\nFalhas: ${failCount}`);
    fetchClients();
    if (selectedClient) fetchTitles(selectedClient.nome);
  };

  const handleChargeClient = async () => {
    if (!selectedClient) return;
    if (!window.confirm(`Enviar cobrança de todos os títulos em aberto para ${selectedClient.nome}?`)) return;
    setActionLoading(true);
    try {
      await api.post(`/crm/clients/${selectedClient.nome}/charge`);
      alert("Cobrança enviada com sucesso!");
    } catch(e) {
      alert("Erro ao enviar cobrança.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleChargeTitle = async (id: number) => {
    setActionLoading(true);
    try {
      await api.post(`/crm/titles/${id}/charge`);
      alert("Título cobrado individualmente com sucesso!");
    } catch(e) {
      alert("Erro ao cobrar título.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleEditInit = () => {
    if (!selectedClient) return;
    setEditClientData({
      contato: selectedClient.contato
    });
    setIsEditingClient(true);
  };

  const handleViewDocuments = async (t: Title) => {
    if (!selectedClient) return;
    setDocsTitle(t);
    setShowDocsDrawer(true);
    setLoadingDocs(true);
    setDocsLista([]);
    try {
      const res = await api.get(`/crm/titles/${encodeURIComponent(t.numero_nf)}/documentos?pagador=${encodeURIComponent(selectedClient.nome)}`);
      setDocsLista(res.data.documentos || []);
    } catch(e) {
      setDocsLista([]);
    }
    setLoadingDocs(false);
  };

  const handleDownloadDoc = (doc: any) => {
    if (doc.id) {
      // Documento indexado no banco - busca como base64
      api.get(`/crm/documentos/${doc.id}/visualizar`).then(res => {
        const { base64, mimetype, filename } = res.data;
        const link = document.createElement('a');
        link.href = `data:${mimetype};base64,${base64}`;
        link.download = filename;
        link.click();
      }).catch(() => alert('Erro ao baixar documento.'));
    } else if (doc.fpath_temp) {
      // Arquivo em temp_data
      api.get(`/crm/documentos/arquivo?fpath=${encodeURIComponent(doc.fpath_temp)}`, { responseType: 'blob' }).then(res => {
        const url = URL.createObjectURL(res.data);
        const link = document.createElement('a');
        link.href = url;
        link.download = doc.filename;
        link.click();
        URL.revokeObjectURL(url);
      }).catch(() => alert('Erro ao baixar arquivo.'));
    }
  };

  const handleOpenDocInTab = (doc: any) => {
    if (doc.id) {
      api.get(`/crm/documentos/${doc.id}/visualizar`).then(res => {
        const { base64, mimetype } = res.data;
        const w = window.open();
        if (w) {
          w.document.write(`<iframe src="data:${mimetype};base64,${base64}" width="100%" height="100%" style="border:none"></iframe>`);
        }
      }).catch(() => alert('Erro ao abrir documento.'));
    }
  };

  const handleUpdateClient = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedClient) return;
    setEditLoading(true);
    try {
      await api.put(`/crm/clients/${selectedClient.id}`, editClientData);
      setIsEditingClient(false);
      setSelectedClient({
        ...selectedClient,
        ...editClientData
      });
      fetchClients();
    } catch(e) {
      alert("Erro ao atualizar dados do cliente.");
    } finally {
      setEditLoading(false);
    }
  };

  const handleDeleteClient = async () => {
    if (!selectedClient) return;
    if (!window.confirm(`Tem certeza que deseja excluir o cliente ${selectedClient.nome}? Todos os títulos deste cliente também serão removidos.`)) return;
    
    setActionLoading(true);
    try {
      await api.delete(`/crm/clients/${selectedClient.id}?nome=${selectedClient.nome}`);
      setSelectedClient(null);
      fetchClients();
    } catch(e) {
      alert("Erro ao excluir cliente.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleNegotiateIA = async () => {
    if (!selectedClient) return;
    setIsNegotiating(true);
    try {
      const res = await api.post('/negotiation/generate', {
        cnpj_empresa: companyCnpj,
        cliente_nome: selectedClient.nome
      });
      setAiProposal(res.data);
      setShowAiModal(true);
    } catch (e: any) {
      alert(e.response?.data?.detail || 'Erro ao gerar negociação com IA');
    }
    setIsNegotiating(false);
  };

  const handleSendAiProposal = async () => {
    if (!selectedClient) return;
    setSendingProposal(true);
    try {
      // O endpoint de geração já registrou no banco, agora enviamos via Evolution
      // Poderíamos ter um endpoint específico /negotiation/send
      const msg = aiProposal.proposta;
      const numeros = selectedClient.whatsapp.split(';').map((n:string) => n.trim()).filter(Boolean);
      
      if (!numeros || numeros.length === 0) {
        alert('Nenhum número de WhatsApp encontrado para o cliente.');
        setSendingProposal(false);
        return;
      }

      await api.post('/negotiation/send', {
        cnpj_empresa: companyCnpj,
        cliente_nome: selectedClient.nome,
        whatsapp_numbers: numeros,
        mensagem: msg
      });
      
      alert('Proposta enviada com sucesso e sessão da IA iniciada!');
      setShowAiModal(false);
    } catch (e: any) {
      alert('Erro ao enviar proposta: ' + (e.response?.data?.detail || e.message));
    }
    setSendingProposal(false);
  };

  const handleSendToCartorio = async () => {
    if (selectedTitleIds.length === 0) {
      alert('Selecione ao menos um título para enviar ao cartório.');
      return;
    }
    
    if (!window.confirm(`Deseja realmente iniciar o envio AUTOMÁTICO de ${selectedTitleIds.length} títulos para o cartório? Esse processo usará o robô Playwright.`)) {
      return;
    }

    setActionLoading(true);
    try {
      const res = await api.post('/cartorio/processar-massa', {
        cnpj_empresa: companyCnpj,
        titulo_ids: selectedTitleIds
      });
      alert(res.data.message);
      setSelectedTitleIds([]);
      if (selectedClient) fetchTitles(selectedClient.nome); // Recarrega para ver status se houver
    } catch (e: any) {
      alert(e.response?.data?.detail || 'Erro ao processar fila de cartório');
    } finally {
      setActionLoading(false);
    }
  };

  const filteredClients = useMemo(() => {
    return clients.filter(c => 
      (c.nome?.toLowerCase() || '').includes(searchTerm.toLowerCase()) || 
      (c.cnpj || '').includes(searchTerm)
    );
  }, [clients, searchTerm]);

  const getStatusColor = (status: string) => {
    switch(status) {
      case 'Aberto': return 'bg-blue-100 text-blue-800 border-blue-200 dark:bg-blue-900/30 dark:text-blue-400 dark:border-blue-800';
      case 'Pago': return 'bg-green-100 text-green-800 border-green-200 dark:bg-green-900/30 dark:text-green-400 dark:border-blue-800';
      case 'Negociado': return 'bg-indigo-100 text-indigo-800 border-indigo-200 dark:bg-indigo-900/30 dark:text-indigo-400 dark:border-indigo-800';
      case 'Cartório': return 'bg-red-100 text-red-800 border-red-200 dark:bg-red-900/30 dark:text-red-400 dark:border-red-800';
      default: return 'bg-slate-100 text-slate-800 border-slate-200 dark:bg-slate-800 py-1 dark:text-slate-300 dark:border-slate-700';
    }
  };

  const displayedTitles = useMemo(() => {
    return titles.filter(t => {
      if (titleFilter === 'pendentes') {
        return !['Pago', 'Baixado', 'Cancelado', 'Cartório'].includes(t.status);
      } else if (titleFilter === 'pagos') {
        return ['Pago', 'Baixado', 'Cancelado'].includes(t.status);
      } else {
        return t.status === 'Cartório';
      }
    });
  }, [titles, titleFilter]);

  return (
    <Layout title="CRM e Gestão Financeira">
      {/* TABS HEADER */}
      <div className="flex border-b border-slate-200 dark:border-dark-border mb-6">
        <button 
          onClick={() => setActiveTab('carteira')}
          className={`px-6 py-3 font-bold text-sm transition-all border-b-2 ${activeTab === 'carteira' ? 'border-primary-500 text-primary-600' : 'border-transparent text-slate-500 hover:text-slate-700'}`}
        >
          📂 Carteira de Clientes
        </button>
        <button 
          onClick={() => setActiveTab('comprovantes')}
          className={`px-6 py-3 font-bold text-sm transition-all border-b-2 flex items-center gap-2 ${activeTab === 'comprovantes' ? 'border-primary-500 text-primary-600' : 'border-transparent text-slate-500 hover:text-slate-700'}`}
        >
          🧾 Comprovantes Recebidos
          {vouchers.filter(v => v.status === 'Pendente').length > 0 && (
            <span className="bg-red-500 text-white text-[10px] px-1.5 py-0.5 rounded-full animate-pulse">
              {vouchers.filter(v => v.status === 'Pendente').length}
            </span>
          )}
        </button>
      </div>

      {activeTab === 'carteira' ? (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-full min-h-[500px]">
        
        {/* CLIENTS LIST */}
        <div className="card lg:h-[calc(100vh-8rem)] h-[400px] flex flex-col p-4 col-span-1 shadow-md">
          <div className="mb-4">
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-bold text-xl dark:text-white flex items-center gap-2">
                Clientes
                {loadingClients && <Loader2 className="animate-spin text-primary-500" size={18} />}
              </h3>
              <button 
                onClick={() => handleChargeAll()}
                disabled={actionLoading}
                className="text-[10px] uppercase font-bold px-3 py-1.5 bg-primary-600 text-white rounded-full hover:bg-primary-700 disabled:opacity-50 transition-all flex items-center gap-1.5 shadow-sm"
              >
                {actionLoading ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />}
                Cobrança Coletiva
              </button>
            </div>
            
            <div className="relative mb-2">
              <Search className="absolute left-3 top-3 text-slate-400" size={18} />
              <input 
                type="text" 
                placeholder="Pesquisar cliente ou CNPJ..." 
                className="input-field pl-10 py-2.5 shadow-sm border-slate-200 focus:ring-2 focus:ring-primary-500/20"
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
              />
            </div>
          </div>
          
          <div className="flex-1 overflow-y-auto pr-2 space-y-2 custom-scrollbar">
            {filteredClients.length === 0 && !loadingClients ? (
              <div className="text-center py-8 text-slate-400 text-sm italic">
                Nenhum cliente encontrado.
              </div>
            ) : (
              filteredClients.map(c => (
                <div 
                  key={c.id} 
                  onClick={() => handleSelectClient(c)}
                  className={`p-4 rounded-xl border-2 cursor-pointer transition-all duration-200 group flex justify-between items-center ${selectedClient?.id === c.id ? 'bg-primary-50 border-primary-500 dark:bg-primary-900/20 dark:border-primary-600' : 'bg-white border-transparent hover:border-slate-200 hover:bg-slate-50 dark:bg-dark-surface dark:border-transparent dark:hover:border-dark-border dark:hover:bg-dark-bg/50'}`}
                >
                  <div className="max-w-[85%]">
                    <div className="font-bold text-slate-900 dark:text-white truncate group-hover:text-primary-600 transition-colors">{c.nome}</div>
                    <div className="text-xs text-slate-500 dark:text-slate-400 font-mono mt-0.5">{c.cnpj}</div>
                  </div>
                  {selectedClient?.id === c.id && <div className="w-2 h-2 rounded-full bg-primary-500 animate-pulse"></div>}
                </div>
              ))
            )}
          </div>
        </div>

        {/* TITLES AREA */}
        <div className="card col-span-1 lg:col-span-2 lg:h-[calc(100vh-8rem)] h-auto min-h-[500px] flex flex-col p-0 overflow-hidden shadow-lg border-slate-200/60 dark:border-dark-border">
          {selectedClient ? (
            <>
              <div className="p-4 lg:p-8 border-b border-slate-200 dark:border-dark-border bg-white dark:bg-dark-surface flex flex-col md:flex-row justify-between items-start gap-4">
                <div className="space-y-1 w-full lg:w-auto">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="px-2 py-0.5 bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400 rounded text-[10px] font-bold uppercase tracking-wider">Cliente Selecionado</span>
                  </div>
                  <h2 className="text-xl lg:text-2xl font-black text-slate-900 dark:text-white leading-tight break-words">{selectedClient.nome}</h2>
                  <div className="flex flex-wrap gap-4 mt-3 text-sm text-slate-600 dark:text-slate-400">
                    <span className="flex items-center gap-1.5"><strong className="font-semibold text-slate-900 dark:text-slate-300">CNPJ:</strong> {selectedClient.cnpj}</span>
                    <span className="flex items-center gap-1.5"><strong className="font-semibold text-slate-900 dark:text-slate-300">WhatsApp:</strong> {selectedClient.whatsapp}</span>
                    <span className="flex items-center gap-1.5"><strong className="font-semibold text-slate-900 dark:text-slate-300">Email:</strong> {selectedClient.email}</span>
                    <span className="flex items-center gap-1.5"><strong className="font-semibold text-slate-900 dark:text-slate-300">Contato:</strong> {selectedClient.contato}</span>
                  </div>
                </div>
                <div className="flex flex-wrap justify-end gap-2 w-full md:w-auto mt-4 md:mt-0">
                  <button 
                    onClick={handleChargeClient}
                    disabled={actionLoading}
                    className="flex-1 md:flex-none flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl bg-green-600 text-white hover:bg-green-700 shadow-md transition-all font-bold disabled:opacity-50 hover:scale-[1.02] active:scale-[0.98]"
                  >
                    {actionLoading ? <Loader2 size={18} className="animate-spin" /> : <Clock size={18} />}
                    Cobrar Títulos
                  </button>
                  <button 
                    onClick={handleNegotiateIA} 
                    disabled={isNegotiating || actionLoading}
                    className="flex-1 md:flex-none flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl bg-primary-600 text-white hover:bg-primary-700 shadow-md transition-all font-bold disabled:opacity-50 hover:scale-[1.02] active:scale-[0.98]"
                  >
                    {isNegotiating ? <Loader2 size={18} className="animate-spin" /> : <Sparkles size={18} />}
                    Negociar c/ IA
                  </button>
                  <button 
                    onClick={handleEditInit}
                    className="p-3 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:text-primary-600 hover:bg-primary-50 transition-all border border-transparent hover:border-primary-200"
                    title="Editar Cliente"
                  >
                    <Edit2 size={18} />
                  </button>
                  <button 
                    onClick={handleDeleteClient}
                    className="p-3 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:text-red-600 hover:bg-red-50 transition-all border border-transparent hover:border-red-200"
                    title="Excluir Cliente"
                  >
                    <Trash2 size={18} />
                  </button>
                </div>
              </div>
              
              <div className="flex-1 overflow-y-auto p-4 lg:p-8 bg-slate-50/30 dark:bg-dark-bg/30">
                <div className="flex items-center justify-between mb-6">
                  <div className="flex flex-col gap-2">
                    <h3 className="text-lg font-black dark:text-white flex items-center gap-3">
                      Carteira de Títulos 
                      <span className="px-3 py-1 bg-primary-100 text-primary-700 dark:bg-primary-900/40 dark:text-primary-400 rounded-full text-xs font-bold">{displayedTitles.length} Títulos</span>
                    </h3>
                    
                    <div className="flex bg-slate-200/50 dark:bg-dark-bg p-1 rounded-xl w-fit mt-1">
                      <button 
                        onClick={() => setTitleFilter('pendentes')}
                        className={`px-4 py-1.5 rounded-lg text-xs font-bold uppercase tracking-wider transition-all ${titleFilter === 'pendentes' ? 'bg-white dark:bg-dark-surface shadow-sm text-primary-600' : 'text-slate-500 hover:text-slate-700 dark:text-slate-400'}`}
                      >
                        Inadimplentes
                      </button>
                      <button 
                        onClick={() => setTitleFilter('pagos')}
                        className={`px-4 py-1.5 rounded-lg text-xs font-bold uppercase tracking-wider transition-all ${titleFilter === 'pagos' ? 'bg-white dark:bg-dark-surface shadow-sm text-green-600' : 'text-slate-500 hover:text-slate-700 dark:text-slate-400'}`}
                      >
                        Pagos / Histórico
                      </button>
                      <button 
                        onClick={() => setTitleFilter('cartorio')}
                        className={`px-4 py-1.5 rounded-lg text-xs font-bold uppercase tracking-wider transition-all ${titleFilter === 'cartorio' ? 'bg-white dark:bg-dark-surface shadow-sm text-red-600' : 'text-slate-500 hover:text-slate-700 dark:text-slate-400'}`}
                      >
                        Cartório
                      </button>
                    </div>
                  </div>
                  {loadingTitles && <Loader2 className="animate-spin text-primary-500" size={20} />}
                </div>

                {displayedTitles.length > 0 && (
                  <div className="mb-4 flex flex-wrap items-center gap-4 bg-white dark:bg-dark-surface p-4 rounded-2xl border border-slate-200 dark:border-dark-border shadow-sm">
                    <div className="flex items-center gap-2">
                      <input 
                        type="checkbox" 
                        checked={displayedTitles.length > 0 && selectedTitleIds.length === displayedTitles.length}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setSelectedTitleIds(displayedTitles.map(t => t.id));
                          } else {
                            setSelectedTitleIds([]);
                          }
                        }}
                        className="w-5 h-5 rounded border-slate-300 text-primary-600 focus:ring-primary-500 cursor-pointer"
                      />
                      <span className="text-sm font-black uppercase text-slate-600 dark:text-slate-400">Selecionar Todos</span>
                    </div>

                    {selectedTitleIds.length > 0 && (
                      <div className="flex flex-wrap items-center gap-2 ml-auto">
                        <span className="text-[10px] font-black uppercase tracking-widest text-primary-600 bg-primary-100 px-3 py-1.5 rounded-full mr-2">
                          {selectedTitleIds.length} Itens
                        </span>
                        <button 
                          onClick={() => handleBulkUpdateStatus('Pago', 'Pausar')}
                          disabled={actionLoading}
                          className="px-4 py-2 text-xs font-black uppercase tracking-wider rounded-xl bg-primary-100 text-primary-700 hover:bg-primary-600 hover:text-white transition-all shadow-sm flex items-center gap-2"
                        >
                          <CheckCircle2 size={16} /> Marcar como Pago
                        </button>
                        <button 
                          onClick={handleSendToCartorio}
                          disabled={actionLoading}
                          className="px-4 py-2 text-xs font-black uppercase tracking-wider rounded-xl bg-red-100 text-red-700 hover:bg-red-600 hover:text-white transition-all shadow-sm flex items-center gap-2"
                        >
                          <Building2 size={16} /> Enviar p/ Cartório
                        </button>
                        <button 
                          onClick={() => handleBulkUpdateStatus('Cancelado', 'Pausar')}
                          disabled={actionLoading}
                          className="px-4 py-2 text-xs font-black uppercase tracking-wider rounded-xl bg-slate-100 text-slate-700 hover:bg-slate-600 hover:text-white transition-all shadow-sm flex items-center gap-2"
                        >
                          <X size={16} /> Cancelar Títulos
                        </button>
                      </div>
                    )}
                  </div>
                )}
                
                {displayedTitles.length === 0 && !loadingTitles ? (
                  <div className="flex flex-col items-center justify-center py-20 text-slate-400 bg-white dark:bg-dark-surface rounded-2xl border-2 border-dashed border-slate-200 dark:border-dark-border">
                    <FileWarning size={48} className="mb-4 opacity-20" />
                    <p className="font-medium">Nenhum título {titleFilter === 'pendentes' ? 'pendente' : titleFilter === 'pagos' ? 'pago' : 'em cartório'} encontrado.</p>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 gap-4">
                    {displayedTitles.map(t => (
                      <div key={t.id} className="border border-slate-200 dark:border-dark-border rounded-2xl p-5 flex flex-col 2xl:flex-row items-start 2xl:items-center justify-between gap-6 bg-white dark:bg-dark-surface shadow-sm hover:shadow-md transition-all">
                        <div className="flex items-start 2xl:items-center gap-4 w-full flex-1">
                          <input 
                            type="checkbox"
                            checked={selectedTitleIds.includes(t.id)}
                            onChange={(e) => {
                              if (e.target.checked) setSelectedTitleIds([...selectedTitleIds, t.id]);
                              else setSelectedTitleIds(selectedTitleIds.filter(id => id !== t.id));
                            }}
                            className="w-5 h-5 rounded border-slate-300 text-primary-600 focus:ring-primary-500 cursor-pointer flex-shrink-0"
                          />
                          <div className="flex-1 w-full min-w-0">
                            <div className="flex flex-wrap items-center gap-3 mb-3">
                            <span className="text-xl font-black text-slate-900 dark:text-white">R$ {(t.valor || 0).toLocaleString('pt-BR', {minimumFractionDigits: 2})}</span>
                            <span className={`px-3 py-1 text-[10px] font-black uppercase tracking-widest rounded-full border-2 ${getStatusColor(t.status)}`}>
                              {t.status}
                            </span>
                          </div>
                          
                          <div className={`grid gap-4 ${titleFilter === 'cartorio' ? 'grid-cols-2 lg:grid-cols-5' : 'grid-cols-2 lg:grid-cols-4'}`}>
                            <div className="space-y-0.5">
                              <p className="text-[10px] text-slate-400 uppercase font-black tracking-tight underline decoration-primary-200">NF / Documento</p>
                              <p className="font-bold text-slate-700 dark:text-slate-300">{t.numero_nf}</p>
                            </div>
                            <div className="space-y-0.5">
                              <p className="text-[10px] text-slate-400 uppercase font-black tracking-tight underline decoration-primary-200">Vencimento</p>
                              <p className="font-bold text-slate-700 dark:text-slate-300">{t.vencimento}</p>
                            </div>
                            {titleFilter === 'cartorio' && (
                              <>
                                <div className="space-y-0.5">
                                  <p className="text-[10px] text-slate-400 uppercase font-black tracking-tight">Enviado em</p>
                                  <p className="font-bold text-slate-700 dark:text-slate-300 text-xs">
                                    {t.data_envio_cartorio ? new Date(t.data_envio_cartorio).toLocaleDateString('pt-BR') : '—'}
                                  </p>
                                </div>
                                <div className="space-y-0.5">
                                  <p className="text-[10px] text-slate-400 uppercase font-black tracking-tight">Retorno</p>
                                  <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-black uppercase ${
                                    t.status_retorno_cartorio === 'Acatado' ? 'bg-green-100 text-green-700' :
                                    t.status_retorno_cartorio === 'Reenviar' ? 'bg-yellow-100 text-yellow-700' :
                                    t.status_retorno_cartorio === 'Notificado' ? 'bg-blue-100 text-blue-700' :
                                    'bg-slate-100 text-slate-500'
                                  }`}>
                                    {t.status_retorno_cartorio || 'Aguardando'}
                                  </span>
                                </div>
                              </>
                            )}
                            <div className="space-y-0.5">
                              <p className="text-[10px] text-slate-400 uppercase font-black tracking-tight underline decoration-primary-200">Fluxo</p>
                              <select 
                                value={t.acao || 'Cobrar'}
                                onChange={(e) => updateTitleStatus(t.id, t.status, e.target.value)}
                                className="text-xs font-bold border-none bg-slate-100 dark:bg-slate-800 rounded-lg px-2 py-1 focus:ring-2 focus:ring-primary-500 w-full"
                              >
                                <option value="Cobrar">Ativo</option>
                                <option value="Pausar">Pausado</option>
                              </select>
                            </div>
                            <div className="space-y-0.5">
                              <p className="text-[10px] text-slate-400 uppercase font-black tracking-tight underline decoration-primary-200">Atualizar</p>
                              <select 
                                value={t.status || 'Aberto'}
                                onChange={(e) => updateTitleStatus(t.id, e.target.value, t.acao)}
                                className="text-xs font-bold border-none bg-slate-100 dark:bg-slate-800 rounded-lg px-2 py-1 focus:ring-2 focus:ring-primary-500 w-full"
                              >
                                <option value="Aberto">Aberto</option>
                                <option value="Pago">Pago</option>
                                <option value="Negociado">Negociado</option>
                                <option value="Cartório">Cartório</option>
                                <option value="Baixado">Arquivo</option>
                                <option value="Cancelado">Cancelado</option>
                              </select>
                            </div>
                          </div>
                        </div>
                        </div>
                        
                        <div className="flex flex-wrap items-center justify-end gap-2 w-full 2xl:w-auto flex-shrink-0 mt-4 2xl:mt-0">
                          <button
                            onClick={() => handleViewDocuments(t)}
                            className="flex-1 md:flex-none px-4 py-3 rounded-xl bg-indigo-600 text-white hover:bg-indigo-700 transition-all shadow-md flex items-center gap-2 group"
                            title="Ver NFe / NFS / Boleto"
                          >
                            <Eye size={18} className="group-hover:scale-110 transition-transform" />
                            <span className="text-xs font-black uppercase">Documentos</span>
                          </button>
                          <button 
                            onClick={() => handleChargeTitle(t.id)}
                            disabled={actionLoading}
                            className="flex-1 md:flex-none p-3 rounded-xl bg-green-500 text-white hover:bg-green-600 transition-all shadow-sm hover:shadow-green-500/20"
                            title="Cobrar este Título agora via WhatsApp"
                          >
                             {actionLoading ? <Loader2 size={20} className="animate-spin" /> : <Send size={20} />}
                          </button>

                          {t.status === 'Aberto' && (
                            <button 
                              onClick={() => updateTitleStatus(t.id, 'Pago', 'Pausar')} 
                              className="flex-1 md:flex-none p-3 rounded-xl bg-primary-100 text-primary-600 hover:bg-primary-600 hover:text-white transition-all border border-transparent"
                              title="Marcar como Pago"
                            >
                              <CheckCircle2 size={20} />
                            </button>
                          )}
                          
                          {t.status === 'Negociado' && (
                            <button 
                              onClick={() => updateTitleStatus(t.id, 'Pago', 'Pausar')} 
                              className="flex-1 md:flex-none p-3 rounded-xl bg-amber-100 text-amber-600 hover:bg-amber-600 hover:text-white transition-all"
                              title="Confirmar Recebimento"
                            >
                              <CheckCircle2 size={20} />
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-slate-300 dark:text-slate-600 bg-slate-50/50 dark:bg-dark-bg/20">
              <div className="p-8 rounded-full bg-white dark:bg-dark-surface shadow-xl mb-6 animate-bounce">
                <Users size={64} className="opacity-20" />
              </div>
              <h4 className="text-xl font-black text-slate-500 dark:text-slate-400">Gestão de Carteira</h4>
              <p className="max-w-xs text-center mt-2 text-slate-400">Selecione um cliente no painel esquerdo para visualizar e gerenciar o fluxo de cobrança.</p>
            </div>
          )}
        </div>
      </div>
      ) : (
        /* COMPROVANTES TAB CONTENT */
        <div className="animate-fade-in space-y-6">
          <div className="flex justify-between items-center bg-white dark:bg-dark-surface p-6 rounded-2xl shadow-sm border border-slate-100 dark:border-dark-border">
            <div>
              <h2 className="text-2xl font-black dark:text-white">Gestão de Comprovantes</h2>
              <p className="text-sm text-slate-500">Confirme ou negue os comprovantes enviados pelos clientes via WhatsApp.</p>
            </div>
            <button onClick={fetchVouchers} className="p-3 rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-dark-bg dark:hover:bg-slate-800 transition-colors">
              <RefreshCw className={loadingVouchers ? "animate-spin" : ""} size={20} />
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
            {vouchers.length === 0 ? (
              <div className="col-span-full py-20 text-center text-slate-400">
                <FileWarning size={64} className="mx-auto mb-4 opacity-10" />
                <p>Nenhum comprovante recebido até o momento.</p>
              </div>
            ) : (
              vouchers.map(v => (
                <div key={v.id} className="card p-0 overflow-hidden flex flex-col border-none shadow-lg hover:shadow-xl transition-shadow bg-white dark:bg-dark-surface">
                  <div className="relative h-48 bg-slate-100 dark:bg-dark-bg flex items-center justify-center group">
                    {v.mimetype.includes('image') ? (
                      <img src={v.arquivo_b64} alt="Comprovante" className="h-full w-full object-cover cursor-pointer hover:scale-105 transition-transform" onClick={() => window.open(v.arquivo_b64)} />
                    ) : (
                      <div className="flex flex-col items-center gap-2 text-slate-400">
                        <FileText size={48} />
                        <span className="text-xs font-bold uppercase">{v.mimetype.split('/')[1]}</span>
                      </div>
                    )}
                    <div className="absolute top-3 left-3">
                      <span className={`px-3 py-1 text-[10px] font-black uppercase tracking-widest rounded-full shadow-sm ${
                        v.status === 'Confirmado' ? 'bg-green-500 text-white' : 
                        v.status === 'Negado' ? 'bg-red-500 text-white' : 'bg-amber-500 text-white animate-pulse'
                      }`}>
                        {v.status}
                      </span>
                    </div>
                  </div>
                  
                  <div className="p-5 flex-1 flex flex-col">
                    <div className="mb-4">
                      <h4 className="font-black text-slate-900 dark:text-white truncate">{v.cliente_nome}</h4>
                      <p className="text-[10px] text-slate-400 font-bold uppercase flex items-center gap-1 mt-1">
                        <Clock size={10} /> Recebido em: {v.recebido_em}
                      </p>
                    </div>

                    {v.status === 'Pendente' && (
                      <div className="mt-auto flex gap-2">
                        <button 
                          onClick={() => handleProcessVoucher(v.id, 'confirmar')}
                          disabled={actionLoading}
                          className="flex-1 bg-green-600 hover:bg-green-700 text-white py-2.5 rounded-xl text-xs font-black uppercase transition-all flex items-center justify-center gap-2"
                        >
                          {actionLoading ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />}
                          Confirmar
                        </button>
                        <button 
                          onClick={() => handleProcessVoucher(v.id, 'negar')}
                          disabled={actionLoading}
                          className="flex-1 bg-red-100 text-red-600 hover:bg-red-600 hover:text-white py-2.5 rounded-xl text-xs font-black uppercase transition-all flex items-center justify-center gap-2"
                        >
                          {actionLoading ? <Loader2 size={14} className="animate-spin" /> : <X size={14} />}
                          Negar
                        </button>
                      </div>
                    )}

                    {v.status !== 'Pendente' && (
                      <div className="mt-auto pt-3 border-t border-slate-100 dark:border-dark-border">
                        <p className="text-[9px] text-slate-400 uppercase font-black">Processado em</p>
                        <p className="text-xs font-bold text-slate-600 dark:text-slate-300">{v.analisado_em || 'Indisponível'}</p>
                      </div>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* MODAL PRÉVIA COBRANÇA COLETIVA */}
      {isShowingPreview && (
        <div className="fixed inset-0 bg-slate-900/70 backdrop-blur-md flex items-center justify-center z-50 p-4 animate-fade-in">
          <div className="card w-full max-w-2xl p-0 shadow-2xl overflow-hidden border-none max-h-[85vh] flex flex-col">
            <div className="p-6 bg-primary-600 text-white flex justify-between items-center">
              <div>
                <h3 className="text-xl font-black">Revisar Cobrança Coletiva</h3>
                <p className="text-xs opacity-80 font-bold uppercase tracking-wider mt-1">Confira a lista de disparos antes de confirmar</p>
              </div>
              <button onClick={() => setIsShowingPreview(false)} className="p-2 hover:bg-white/10 rounded-lg transition-colors">
                 <X size={24} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-6 space-y-4 custom-scrollbar">
              {previewData.length === 0 ? (
                <div className="text-center py-10 text-slate-500">
                   <AlertCircle className="mx-auto mb-2 opacity-20" size={48} />
                   <p className="font-bold">Nenhum título em aberto elegível para cobrança automática.</p>
                </div>
              ) : (
                previewData.map((item, idx) => (
                  <div key={idx} className="rounded-2xl border border-slate-100 dark:border-dark-border bg-white dark:bg-dark-surface shadow-sm overflow-hidden">
                    <div 
                      onClick={() => togglePreviewExpand(item.cliente)}
                      className="p-4 flex items-center justify-between cursor-pointer hover:bg-slate-50 dark:hover:bg-dark-bg/50 transition-colors"
                    >
                      <div className="flex-1 min-w-0 pr-4">
                        <p className="font-bold text-slate-900 dark:text-white truncate">{item.cliente}</p>
                        <div className="flex gap-4 mt-1">
                          <span className="text-[10px] font-black uppercase text-primary-500">{item.qtd_titulos} Títulos Ativos</span>
                          <div className="flex gap-2">
                            {item.whatsapp && <span className="w-2 h-2 rounded-full bg-green-500" title="WhatsApp OK"></span>}
                            {item.email && <span className="w-2 h-2 rounded-full bg-blue-500" title="Email OK"></span>}
                          </div>
                        </div>
                      </div>
                      <div className="text-right flex items-center gap-4">
                        <div>
                           <p className="font-black text-slate-900 dark:text-white">R$ {(item.valor_total || 0).toLocaleString('pt-BR', {minimumFractionDigits: 2})}</p>
                          <p className="text-[10px] text-slate-500 uppercase font-bold">Total</p>
                        </div>
                        <ChevronDown className={`text-slate-400 transition-transform duration-300 ${expandedPreviewClients.includes(item.cliente) ? 'rotate-180' : ''}`} size={20} />
                      </div>
                    </div>

                    {/* LISTA DE TÍTULOS EXPANSÍVEL */}
                    {expandedPreviewClients.includes(item.cliente) && (
                      <div className="bg-slate-50/50 dark:bg-dark-bg/20 border-t border-slate-100 dark:border-dark-border p-4 space-y-2">
                        {item.itens.map((title: any) => (
                          <div key={title.id} className="flex items-center justify-between bg-white dark:bg-dark-surface p-3 rounded-xl border border-slate-100 dark:border-dark-border shadow-sm">
                            <div className="grid grid-cols-3 gap-8 flex-1">
                              <div>
                                <p className="text-[9px] text-slate-400 uppercase font-black">NF</p>
                                <p className="text-xs font-bold text-slate-700 dark:text-slate-300">{title.numero_nf}</p>
                              </div>
                              <div>
                                <p className="text-[9px] text-slate-400 uppercase font-black">Vencimento</p>
                                <p className="text-xs font-bold text-slate-700 dark:text-slate-300">{title.vencimento}</p>
                              </div>
                              <div>
                                <p className="text-[9px] text-slate-400 uppercase font-black">Valor Total</p>
                                 <p className="text-xs font-black text-slate-900 dark:text-white">R$ {(title.total || 0).toLocaleString('pt-BR', {minimumFractionDigits: 2})}</p>
                              </div>
                            </div>
                            <div className="flex items-center gap-2">
                               <span className={`text-[10px] font-black uppercase px-2 py-0.5 rounded-full ${title.acao === 'Cobrar' ? 'bg-green-100 text-green-700' : 'bg-slate-200 text-slate-600'}`}>
                                 {title.acao === 'Cobrar' ? 'Ativo' : 'Pausado'}
                               </span>
                               <button 
                                 onClick={async () => {
                                   const newAction = title.acao === 'Cobrar' ? 'Pausar' : 'Cobrar';
                                   await updateTitleStatus(title.id, title.status, newAction);
                                   // Refresh preview silently
                                   handleChargeAll(true);
                                 }}
                                 className="p-1.5 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg transition-colors text-slate-400 hover:text-primary-600"
                                 title={title.acao === 'Cobrar' ? 'Pausar Cobrança para este título' : 'Ativar Cobrança'}
                               >
                                 {title.acao === 'Cobrar' ? <Power size={14} className="text-red-400" /> : <Power size={14} className="text-green-500" />}
                               </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>

            <div className="p-6 border-t border-slate-100 dark:border-dark-border bg-slate-50/30 dark:bg-dark-surface flex flex-col gap-5">
              
              <div className="flex flex-col">
                <span className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-2 ml-1">Canais de Comunicação</span>
                <div className="flex bg-slate-200/50 dark:bg-dark-bg p-1.5 rounded-2xl shadow-inner border border-slate-200 dark:border-dark-border w-full">
                  <button 
                    onClick={() => setSelectedChannels('email')} 
                    className={`px-3 py-2.5 text-xs font-bold rounded-xl transition-all flex-1 ${selectedChannels === 'email' ? 'bg-white dark:bg-slate-700 shadow-sm text-primary-600' : 'text-slate-500 hover:text-slate-700 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'}`}
                  >
                    ✉️ Só E-mail
                  </button>
                  <button 
                    onClick={() => setSelectedChannels('whatsapp')} 
                    className={`px-3 py-2.5 text-xs font-bold rounded-xl transition-all flex-1 ${selectedChannels === 'whatsapp' ? 'bg-white dark:bg-slate-700 shadow-sm text-green-600' : 'text-slate-500 hover:text-slate-700 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'}`}
                  >
                    💬 Só WhatsApp
                  </button>
                  <button 
                    onClick={() => setSelectedChannels('ambos')} 
                    className={`px-3 py-2.5 text-xs font-bold rounded-xl transition-all flex-[1.2] ${selectedChannels === 'ambos' ? 'bg-white dark:bg-slate-700 shadow-sm text-indigo-600' : 'text-slate-500 hover:text-slate-700 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'}`}
                  >
                    🚀 Ambos os Canais
                  </button>
                </div>
              </div>

              <div className="flex gap-4 w-full">
                  <button 
                    onClick={() => setIsShowingPreview(false)} 
                    className="flex-[0.8] py-3.5 px-4 text-sm font-bold text-slate-600 bg-white dark:bg-dark-bg hover:bg-slate-100 dark:hover:bg-slate-800 rounded-xl transition-all border border-slate-200 dark:border-dark-border"
                  >
                    Cancelar
                  </button>
                  <button 
                    onClick={confirmChargeAll}
                    disabled={previewData.length === 0 || actionLoading}
                    className="flex-[2] bg-primary-600 hover:bg-primary-700 text-white py-3.5 px-6 rounded-xl font-black shadow-lg shadow-primary-500/20 flex justify-center items-center gap-2 disabled:opacity-50 transition-all hover:scale-[1.02]"
                  >
                    <Send size={18} />
                    Confirmar Disparos
                  </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* MODAL EDITAR CLIENTE */}
      {isEditingClient && (
        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-md flex items-center justify-center z-50 p-4 animate-fade-in">
          <div className="card w-full max-w-lg p-8 shadow-2xl overflow-y-auto max-h-[90vh] border-none">
            <div className="flex justify-between items-center mb-8">
              <div>
                <h3 className="text-2xl font-black dark:text-white">Editar Cliente</h3>
                <p className="text-xs text-slate-500 font-bold uppercase tracking-widest mt-1">Atualização Cadastral</p>
              </div>
              <button onClick={() => setIsEditingClient(false)} className="p-2 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-xl transition-colors">
                 <X size={24} className="text-slate-400" />
              </button>
            </div>

            <form onSubmit={handleUpdateClient} className="space-y-6">
              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1.5 ml-1">Razão Social / Nome</label>
                  <input 
                    type="text" required 
                    value={editClientData.nome} 
                    onChange={e => setEditClientData({...editClientData, nome: e.target.value})} 
                    className="input-field bg-slate-50 dark:bg-slate-800/50 border-slate-200 dark:border-slate-700 p-3 text-sm font-bold" 
                  />
                </div>
                <div>
                  <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1.5 ml-1">CNPJ</label>
                  <input 
                    type="text" required 
                    value={editClientData.cnpj} 
                    onChange={e => setEditClientData({...editClientData, cnpj: e.target.value})} 
                    className="input-field bg-slate-50 dark:bg-slate-800/50 border-slate-200 dark:border-slate-700 p-3 text-sm font-bold" 
                  />
                </div>
                
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1.5 ml-1">WhatsApp</label>
                    <input 
                      type="text" 
                      value={editClientData.whatsapp} 
                      onChange={e => setEditClientData({...editClientData, whatsapp: e.target.value})} 
                      className="input-field bg-slate-50 dark:bg-slate-800/50 border-slate-200 dark:border-slate-700 p-3 text-sm font-bold" 
                      placeholder="Ex: 5511999999999; 5511888888888" 
                    />
                    <p className="text-[10px] text-slate-400 mt-1 ml-1 font-bold italic">Separe múltiplos números com ";"</p>
                  </div>
                  <div>
                    <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1.5 ml-1">E-mail</label>
                    <input 
                      type="text" 
                      value={editClientData.email} 
                      onChange={e => setEditClientData({...editClientData, email: e.target.value})} 
                      className="input-field bg-slate-50 dark:bg-slate-800/50 border-slate-200 dark:border-slate-700 p-3 text-sm font-bold" 
                      placeholder="Ex: financeiro@email.com; contato@email.com"
                    />
                    <p className="text-[10px] text-slate-400 mt-1 ml-1 font-bold italic">Separe múltiplos e-mails com ";"</p>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1.5 ml-1">Ponto de Contato</label>
                  <input 
                    type="text" 
                    value={editClientData.contato} 
                    onChange={e => setEditClientData({...editClientData, contato: e.target.value})} 
                    className="input-field bg-slate-50 dark:bg-slate-800/50 border-slate-200 dark:border-slate-700 p-3 text-sm font-bold" 
                  />
                </div>
              </div>

              <div className="flex gap-4 pt-6 mt-4 border-t border-slate-100 dark:border-slate-800">
                <button type="button" onClick={() => setIsEditingClient(false)} className="flex-1 py-3 text-sm font-bold text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 transition-colors">Descartar</button>
                <button 
                  type="submit" 
                  disabled={editLoading} 
                  className="flex-[2] btn-primary py-3 rounded-xl flex justify-center items-center gap-2 shadow-lg shadow-primary-500/20"
                >
                  {editLoading ? <Loader2 className="animate-spin" size={20} /> : 'Salvar Dados'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
      {/* MODAL DE PROGRESSO DE ENVIO EM MASSA */}
      {isChargingBulk && (
        <div className="fixed inset-0 bg-slate-900/80 backdrop-blur-sm z-[60] flex items-center justify-center p-4">
          <div className="bg-white dark:bg-dark-surface rounded-3xl shadow-2xl w-full max-w-md p-8 text-center animate-in zoom-in duration-300">
            <div className="mb-6 relative flex justify-center">
              <div className="w-24 h-24 rounded-full border-4 border-slate-100 dark:border-dark-border flex items-center justify-center shadow-inner">
                 <Loader2 size={40} className="text-primary-500 animate-spin" />
              </div>
              <div className="absolute top-0 right-1/4 bg-primary-500 text-white text-[10px] h-6 w-6 flex items-center justify-center rounded-full font-black animate-bounce">
                {Math.round((bulkProgress / bulkTotal) * 100)}%
              </div>
            </div>
            
            <h3 className="text-2xl font-black text-slate-900 dark:text-white mb-2">Processando Disparos</h3>
            <p className="text-sm text-slate-500 mb-6">Enviando cobranças para sua carteira...</p>
            
            <div className="space-y-4">
              <div className="flex justify-between items-center text-xs font-bold uppercase tracking-wider">
                <span className="text-primary-600">Progresso</span>
                <span className="text-slate-400">{bulkProgress} / {bulkTotal}</span>
              </div>
              
              <div className="h-3 w-full bg-slate-100 dark:bg-dark-bg rounded-full overflow-hidden shadow-inner">
                <div 
                  className="h-full bg-primary-500 transition-all duration-500 ease-out shadow-[0_0_15px_rgba(var(--primary-rgb),0.5)]"
                  style={{ width: `${(bulkProgress / bulkTotal) * 100}%` }}
                />
              </div>

              <div className="pt-4 px-4 py-3 bg-slate-50 dark:bg-dark-bg/50 rounded-2xl border border-slate-100 dark:border-dark-border">
                <p className="text-[10px] text-slate-400 uppercase font-black mb-1">Enviando agora para:</p>
                <p className="text-sm font-bold text-slate-700 dark:text-slate-200 truncate">{currentChargingName || 'Iniciando...'}</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* AI NEGOTIATION MODAL */}
      {showAiModal && (
        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4 overflow-y-auto">
          <div className="bg-white dark:bg-dark-surface rounded-2xl shadow-2xl w-full max-w-2xl overflow-hidden animate-in fade-in zoom-in duration-300">
            <div className="p-6 border-b border-slate-100 dark:border-dark-border flex justify-between items-center bg-primary-50 dark:bg-primary-900/10">
              <h3 className="text-xl font-black text-primary-700 dark:text-primary-400 flex items-center gap-2">
                <Sparkles size={24} /> Proposta de Negociação IA
              </h3>
              <button onClick={() => setShowAiModal(false)} className="text-slate-400 hover:text-slate-600 transition-colors">
                <X size={24} />
              </button>
            </div>
            <div className="p-8">
              <div className="bg-slate-50 dark:bg-dark-bg/50 p-4 rounded-xl border border-slate-100 dark:border-dark-border mb-6">
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-slate-500 block">Cliente</span>
                    <span className="font-bold dark:text-white uppercase">{aiProposal.cliente}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Total em Aberto</span>
                    <span className="font-bold text-primary-600">R$ {(aiProposal.total || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}</span>
                  </div>
                </div>
              </div>
              
              <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-2">Mensagem Gerada pelo Gemini (RAG)</label>
              <textarea 
                className="input-field min-h-[250px] font-sans text-base leading-relaxed" 
                value={aiProposal.proposta}
                onChange={e => setAiProposal({...aiProposal, proposta: e.target.value})}
              />
              <p className="text-[10px] text-slate-400 mt-2 italic">* Você pode editar a mensagem acima antes de disparar para o WhatsApp.</p>
            </div>
            <div className="p-6 bg-slate-50 dark:bg-dark-surface border-t border-slate-100 dark:border-dark-border flex justify-end gap-3">
              <button onClick={() => setShowAiModal(false)} className="px-6 py-2.5 text-sm font-bold text-slate-500 hover:text-slate-700">Cancelar</button>
              <button 
                onClick={handleSendAiProposal}
                disabled={sendingProposal}
                className="btn-primary px-8 flex items-center justify-center"
              >
                {sendingProposal ? <Loader2 size={18} className="animate-spin mr-2"/> : <Send size={18} className="mr-2"/>}
                Confirmar e Enviar via WhatsApp
              </button>
            </div>
          </div>
        </div>
      )}

      {/* DRAWER DE DOCUMENTOS (NFe / NFS / Boleto) */}
      {showDocsDrawer && (
        <div className="fixed inset-0 z-50 flex justify-end" onClick={() => setShowDocsDrawer(false)}>
          <div
            className="w-full max-w-md h-full bg-white dark:bg-dark-surface shadow-2xl flex flex-col animate-in slide-in-from-right duration-300"
            onClick={e => e.stopPropagation()}
          >
            {/* Header */}
            <div className="p-6 border-b border-slate-100 dark:border-dark-border flex justify-between items-start bg-indigo-50 dark:bg-indigo-900/10">
              <div>
                <p className="text-[10px] font-black uppercase tracking-widest text-indigo-400 mb-1">Documentos Fiscais</p>
                <h3 className="text-lg font-black text-indigo-800 dark:text-indigo-300">NF {docsTitle?.numero_nf}</h3>
                <p className="text-xs text-slate-500 mt-1">Venc. {docsTitle?.vencimento} · R$ {(docsTitle?.valor || 0).toLocaleString('pt-BR', {minimumFractionDigits: 2})}</p>
              </div>
              <button onClick={() => setShowDocsDrawer(false)} className="p-2 rounded-xl bg-white dark:bg-dark-bg text-slate-400 hover:text-slate-700 transition-colors shadow-sm">
                <X size={18} />
              </button>
            </div>

            {/* Body */}
            <div className="flex-1 overflow-y-auto p-6 space-y-3">
              {loadingDocs ? (
                <div className="flex flex-col items-center justify-center py-20 text-slate-400">
                  <Loader2 size={36} className="animate-spin mb-3 text-indigo-500" />
                  <p className="text-sm">Buscando documentos...</p>
                </div>
              ) : docsLista.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-20 text-slate-400">
                  <FileWarning size={48} className="mb-3 opacity-20" />
                  <p className="font-medium text-sm">Nenhum documento encontrado</p>
                  <p className="text-xs mt-1 text-center max-w-[220px]">A Analu ainda não indexou arquivos para esta NF. Eles são capturados automaticamente dos e-mails.</p>
                </div>
              ) : (
                docsLista.map((doc, i) => (
                  <div key={i} className="flex items-center gap-4 p-4 rounded-2xl border border-slate-200 dark:border-dark-border bg-slate-50 dark:bg-dark-bg hover:border-indigo-300 transition-all group">
                    <div className={`w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0 font-black text-xs uppercase ${doc.ext === '.pdf' ? 'bg-red-100 text-red-600' : 'bg-green-100 text-green-600'}`}>
                      {doc.ext === '.pdf' ? 'PDF' : 'XML'}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-bold text-slate-800 dark:text-slate-200 text-sm truncate">{doc.filename}</p>
                      <p className="text-[10px] text-slate-400 uppercase font-bold mt-0.5">{doc.tipo || 'Documento'} · {doc.created_at ? new Date(doc.created_at).toLocaleDateString('pt-BR') : '—'}</p>
                    </div>
                    <div className="flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                      {doc.ext === '.pdf' && doc.id && (
                        <button
                          onClick={() => handleOpenDocInTab(doc)}
                          className="p-2 rounded-lg bg-indigo-100 text-indigo-600 hover:bg-indigo-600 hover:text-white transition-all"
                          title="Abrir PDF"
                        >
                          <Eye size={16} />
                        </button>
                      )}
                      <button
                        onClick={() => handleDownloadDoc(doc)}
                        className="p-2 rounded-lg bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300 hover:bg-indigo-600 hover:text-white transition-all"
                        title="Baixar"
                      >
                        <FileDown size={16} />
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* Footer */}
            <div className="p-4 border-t border-slate-100 dark:border-dark-border bg-slate-50 dark:bg-dark-bg/30">
              <p className="text-[10px] text-slate-400 text-center">
                Documentos capturados automaticamente pela Analu a partir dos e-mails enviados.
              </p>
            </div>
          </div>
        </div>
      )}

    </Layout>
  );
};
