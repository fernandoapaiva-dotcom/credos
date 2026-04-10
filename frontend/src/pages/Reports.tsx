import React, { useState, useEffect } from 'react';
import { Layout } from '../components/ui/Layout';
import { api, useAuth } from '../context/AuthContext';
import { FileText, Download, Loader2 } from 'lucide-react';

interface Client {
  id: number;
  nome: string;
}

export const Reports: React.FC = () => {
  const { companyCnpj } = useAuth();
  const [clientes, setClientes] = useState<Client[]>([]);
  const [downloading, setDownloading] = useState(false);

  // Form
  const [cliente, setCliente] = useState('Todos');
  const [dataInicio, setDataInicio] = useState(new Date().toISOString().split('T')[0]);
  const [dataFim, setDataFim] = useState(new Date().toISOString().split('T')[0]);
  const [tipo, setTipo] = useState('Todos');

  useEffect(() => {
    if (companyCnpj) {
      fetchClients();
    }
  }, [companyCnpj]);

  const fetchClients = async () => {
    try {
      const res = await api.get('/crm/clients');
      setClientes(res.data.clients || []);
    } catch(e) {
      console.error("Erro ao buscar clientes:", e);
    }
  };

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!dataInicio || !dataFim) {
      alert("Preencha as datas.");
      return;
    }

    const token = localStorage.getItem('token');
    
    if (!companyCnpj || !token) {
      alert("Sessão ou Empresa não identificada. Selecione uma unidade no Dashboard.");
      return;
    }

    setDownloading(true);
    
    // Timeout de 60 segundos para evitar hang infinito no UI
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 60000);

    try {
      const response = await fetch(`${window.location.origin}/api/reports/generate?t=${Date.now()}`, {
        method: 'POST',
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
          'x-company-cnpj': companyCnpj
        },
        body: JSON.stringify({
          cliente,
          data_inicio: dataInicio,
          data_fim: dataFim,
          tipo
        })
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        let errorMsg = "Erro ao gerar relatório.";
        try {
          const errData = await response.json();
          errorMsg = errData.detail || errorMsg;
        } catch(e) {}
        throw new Error(errorMsg);
      }

      const blob = await response.blob();
      
      // Extract filename from Content-Disposition header
      const contentDisposition = response.headers.get('content-disposition');
      
      // Sanitize filename to avoid Chrome security blocks on HTTP
      const safeType = tipo.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-z0-9]/gi, '_').toLowerCase();
      let filename = `relatorio_${safeType}.pdf`;
      
      if (contentDisposition) {
        const filenameMatch = contentDisposition.match(/filename="?([^";]+)"?/);
        if (filenameMatch && filenameMatch[1]) {
          filename = filenameMatch[1];
        }
      }

      // Download file
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      
      // Cleanup
      setTimeout(() => {
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);
      }, 100);

    } catch (err: any) {
      if (err.name === 'AbortError') {
        alert("O download demorou demais e foi interrompido. Verifique sua conexão e tente novamente.");
      } else {
        console.error("Erro na geração do relatório:", err);
        alert(err.message || "Erro ao receber o arquivo. Tente novamente.");
      }
    } finally {
      clearTimeout(timeoutId);
      setDownloading(false);
    }
  };

  return (
    <Layout title="Relatórios e Auditoria">
      <div className="card max-w-2xl mx-auto p-8 animate-slide-up relative overflow-hidden">
        
        {/* OVERLAY DE DOWNLOAD */}
        {downloading && (
          <div className="absolute inset-0 bg-white/80 dark:bg-dark-bg/80 backdrop-blur-sm z-50 flex flex-col items-center justify-center animate-fade-in">
            <div className="p-6 bg-white dark:bg-dark-surface rounded-3xl shadow-2xl flex flex-col items-center text-center">
              <div className="w-16 h-16 mb-4 rounded-full border-4 border-primary-100 dark:border-primary-900/30 flex items-center justify-center">
                <Loader2 className="text-primary-500 animate-spin" size={32} />
              </div>
              <h3 className="text-lg font-black dark:text-white">Gerando Relatório</h3>
              <p className="text-xs text-slate-500 mt-1 uppercase font-bold tracking-widest">Aguarde a exportação dos dados...</p>
            </div>
          </div>
        )}

        <div className="flex items-center gap-4 mb-6 border-b border-slate-200 dark:border-dark-border pb-6">
          <div className="p-3 bg-primary-100 text-primary-600 rounded-xl dark:bg-primary-900/40 dark:text-primary-400">
            <FileText size={32} />
          </div>
          <div>
            <h2 className="text-xl font-bold dark:text-white mb-1">Painel Analítico de Auditoria</h2>
            <p className="text-sm text-slate-500 dark:text-slate-400">Extração dinâmica de atividades por filial e cliente.</p>
          </div>
        </div>

        {/* AVISO DE SEGURANÇA HTTP */}
        {window.location.protocol !== 'https:' && (
          <div className="mb-6 p-4 bg-blue-50 dark:bg-blue-900/10 border border-blue-200 dark:border-blue-800 rounded-2xl flex items-start gap-4 shadow-sm">
            <div className="p-2 bg-blue-100 dark:bg-blue-800 text-blue-600 dark:text-blue-300 rounded-lg shrink-0">
               <Download size={16} />
            </div>
            <div>
              <p className="text-xs font-black uppercase text-blue-800 dark:text-blue-300 mb-0.5">Aviso de Download Seguro</p>
              <p className="text-[11px] text-blue-600 dark:text-blue-400 leading-normal">
                Como este portal utiliza conexão HTTP, o seu navegador pode bloquear o download inicial. 
                Se um aviso de <b>"Download não seguro"</b> aparecer, clique em <b>"Manter"</b> ou <b>"Autorizar"</b> para receber o PDF.
              </p>
            </div>
          </div>
        )}

        {!companyCnpj ? (
          <div className="py-10 text-center space-y-4">
             <div className="p-4 bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400 rounded-xl text-sm font-medium border border-amber-200 dark:border-amber-800">
                Selecione uma empresa/filial no Dashboard para habilitar os relatórios.
             </div>
          </div>
        ) : (
          <form onSubmit={handleGenerate} className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-700 dark:text-slate-300">Cliente</label>
                <select className="input-field py-2.5" value={cliente} onChange={e => setCliente(e.target.value)}>
                  <option value="Todos">Todos os Clientes</option>
                  {clientes.map(c => (
                    <option key={c.id} value={c.nome}>{c.nome}</option>
                  ))}
                </select>
              </div>
              
              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-700 dark:text-slate-300">Status / Operação</label>
                <select className="input-field py-2.5" value={tipo} onChange={e => setTipo(e.target.value)}>
                  <option value="Cobrados">TÍTULOS COBRADOS (OPERADOR & ANALU)</option>
                  <option value="Baixados">TÍTULOS BAIXADOS</option>
                  <option value="Cancelados">TÍTULOS CANCELADOS</option>
                  <option value="Excluidos">TÍTULOS EXCLUÍDOS</option>
                  <option value="Solicitado_Cartorio">TÍTULOS SOLICITADOS PARA CARTÓRIO (OPERADOR)</option>
                  <option value="Enviado_Cartorio">TÍTULOS ENVIADOS PARA CARTÓRIO (ANALU IA)</option>
                </select>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-700 dark:text-slate-300">Data de Início</label>
                <input type="date" required value={dataInicio} onChange={e => setDataInicio(e.target.value)} className="input-field py-2.5" />
              </div>
              
              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-700 dark:text-slate-300">Data de Fim</label>
                <input type="date" required value={dataFim} onChange={e => setDataFim(e.target.value)} className="input-field py-2.5" />
              </div>
            </div>

            <div className="pt-4 flex justify-end">
              <button type="submit" disabled={downloading} className="btn-primary w-full md:w-auto px-8 py-3">
                {downloading ? 'Gerando...' : <span className="flex items-center gap-2"><Download size={18}/> Processar e Baixar PDF</span>}
              </button>
            </div>
          </form>
        )}

      </div>
    </Layout>
  );
};
