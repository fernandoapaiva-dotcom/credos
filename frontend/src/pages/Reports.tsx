import React, { useState, useEffect } from 'react';
import { Layout } from '../components/ui/Layout';
import { api } from '../context/AuthContext';
import { FileText, Download } from 'lucide-react';

interface Client {
  id: number;
  nome: string;
}

export const Reports: React.FC = () => {
  const [clientes, setClientes] = useState<Client[]>([]);
  const [downloading, setDownloading] = useState(false);

  // Form
  const [cliente, setCliente] = useState('Todos');
  const [dataInicio, setDataInicio] = useState(new Date().toISOString().split('T')[0]);
  const [dataFim, setDataFim] = useState(new Date().toISOString().split('T')[0]);
  const [tipo, setTipo] = useState('Todos');

  useEffect(() => {
    fetchClients();
  }, []);

  const fetchClients = async () => {
    try {
      const res = await api.get('/crm/clients');
      setClientes(res.data.clients || []);
    } catch(e) {}
  };

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!dataInicio || !dataFim) {
      alert("Preencha as datas.");
      return;
    }
    setDownloading(true);
    try {
      const response = await api.post('/reports/generate', {
        cliente,
        data_inicio: dataInicio,
        data_fim: dataFim,
        tipo
      }, {
        responseType: 'blob'
      });

      // Extract filename from Content-Disposition header
      const contentDisposition = response.headers['content-disposition'];
      let filename = `relatorio_${tipo.toLowerCase().replace(/ /g, '_')}.pdf`;
      
      if (contentDisposition) {
        const filenameMatch = contentDisposition.match(/filename="?([^"]+)"?/);
        if (filenameMatch && filenameMatch[1]) {
          filename = filenameMatch[1];
        }
      }

      // Download file
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      link.parentNode?.removeChild(link);

    } catch (err: any) {
      alert("Nenhum dado encontrado ou erro ao gerar o PDF.");
    } finally {
      setDownloading(false);
    }
  };

  return (
    <Layout title="Relatórios e Auditoria">
      <div className="card max-w-2xl mx-auto p-8 animate-slide-up">
        
        <div className="flex items-center gap-4 mb-6 border-b border-slate-200 dark:border-dark-border pb-6">
          <div className="p-3 bg-primary-100 text-primary-600 rounded-xl dark:bg-primary-900/40 dark:text-primary-400">
            <FileText size={32} />
          </div>
          <div>
            <h2 className="text-xl font-bold dark:text-white mb-1">Gerar Relatório Analítico</h2>
            <p className="text-sm text-slate-500 dark:text-slate-400">O novo layout otimizado poupa espaço em folha e cruza todos os dados.</p>
          </div>
        </div>

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
                {/* Status dos Títulos */}
                <option value="Todos">Todos os Títulos</option>
                <option value="Aberto">Títulos em Aberto</option>
                <option value="Pagos">Títulos Pagos / Baixados</option>
                <option value="Cartório">Títulos em Cartório</option>
                {/* Relatórios de Atividade */}
                <option value="Cobrados">Atividades do Período (Cobranças + Movimentações)</option>
                <option value="Historico">Histórico de Cobranças (Logs de Envio)</option>
                <option value="Exclusoes">Histórico de Exclusões</option>
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

      </div>
    </Layout>
  );
};
