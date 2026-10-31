import React, { useState, useEffect } from 'react';
import { Layout } from '../components/ui/Layout';
import { api, useAuth } from '../context/AuthContext';
import { FileText, Download, Loader2, Upload, Search } from 'lucide-react';

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
  const [tipo, setTipo] = useState('Cobrancas_Diarias');

  // Confrontation Tab State
  const [activeTab, setActiveTab] = useState<'logs' | 'confront'>('logs');
  const [confrontFile, setConfrontFile] = useState<File | null>(null);
  const [confronting, setConfronting] = useState(false);
  const [confrontResult, setConfrontResult] = useState<{ columns: string[], rows: any[] } | null>(null);
  const [exporting, setExporting] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('Todos');

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

  const handleConfront = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!confrontFile) {
      alert("Por favor, selecione um arquivo PDF.");
      return;
    }

    const token = localStorage.getItem('token');
    if (!companyCnpj || !token) {
      alert("Sessão ou Empresa não identificada.");
      return;
    }

    setConfronting(true);
    const formData = new FormData();
    formData.append('file', confrontFile);

    try {
      const response = await fetch(`${window.location.origin}/api/reports/confront-pdf`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'x-company-cnpj': companyCnpj
        },
        body: formData
      });

      if (!response.ok) {
        throw new Error("Erro ao confrontar o PDF. Verifique o arquivo e tente novamente.");
      }

      const data = await response.json();
      setConfrontResult(data);
    } catch(err: any) {
      console.error("Erro ao confrontar:", err);
      alert(err.message || "Erro de conexão.");
    } finally {
      setConfronting(false);
    }
  };

  const handleExportConfront = async () => {
    if (!confrontResult) return;
    
    const token = localStorage.getItem('token');
    if (!companyCnpj || !token) return;

    setExporting(true);
    try {
      const response = await fetch(`${window.location.origin}/api/reports/export-confront-pdf`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
          'x-company-cnpj': companyCnpj
        },
        body: JSON.stringify(confrontResult)
      });

      if (!response.ok) {
        throw new Error("Erro ao exportar PDF.");
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'relatorio_confronto_boletos.pdf');
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch(err: any) {
      console.error("Erro ao exportar:", err);
      alert(err.message || "Erro ao baixar o PDF.");
    } finally {
      setExporting(false);
    }
  };

  // Filtered rows for confrontation result
  const filteredRows = (confrontResult?.rows || []).filter(row => {
    // search term matching
    const searchMatch = Object.values(row).some(val => 
      String(val).toLowerCase().includes(searchTerm.toLowerCase())
    );
    
    // status filter matching
    if (statusFilter === 'Todos') return searchMatch;
    
    const statusCredos = String(row['Status Credos'] || '').toLowerCase();
    const filterLower = statusFilter.toLowerCase();
    
    if (filterLower === 'pago') return searchMatch && (statusCredos === 'pago' || statusCredos === 'baixado');
    if (filterLower === 'aberto') return searchMatch && (statusCredos === 'aberto' || statusCredos === 'manter aberto');
    return searchMatch && statusCredos === filterLower;
  });

  return (
    <Layout title="Relatórios e Auditoria">
      <div className={`card ${activeTab === 'confront' && confrontResult ? 'max-w-6xl' : 'max-w-2xl'} mx-auto p-8 animate-slide-up relative overflow-hidden transition-all duration-300`}>
        
        {/* OVERLAY DE DOWNLOAD / CONFRONTO */}
        {(downloading || confronting || exporting) && (
          <div className="absolute inset-0 bg-white/80 dark:bg-dark-bg/80 backdrop-blur-sm z-50 flex flex-col items-center justify-center animate-fade-in">
            <div className="p-6 bg-white dark:bg-dark-surface rounded-3xl shadow-2xl flex flex-col items-center text-center">
              <div className="w-16 h-16 mb-4 rounded-full border-4 border-primary-100 dark:border-primary-900/30 flex items-center justify-center">
                <Loader2 className="text-primary-500 animate-spin" size={32} />
              </div>
              <h3 className="text-lg font-black dark:text-white">
                {downloading ? 'Gerando Relatório' : confronting ? 'Confrontando Boletos' : 'Exportando PDF'}
              </h3>
              <p className="text-xs text-slate-500 mt-1 uppercase font-bold tracking-widest">Aguarde a operação dos dados...</p>
            </div>
          </div>
        )}

        <div className="flex items-center gap-4 mb-6 border-b border-slate-200 dark:border-dark-border pb-6">
          <div className="p-3 bg-primary-100 text-primary-600 rounded-xl dark:bg-primary-900/40 dark:text-primary-400">
            <FileText size={32} />
          </div>
          <div className="flex-1">
            <h2 className="text-xl font-bold dark:text-white mb-1">Painel Analítico de Auditoria</h2>
            <p className="text-sm text-slate-500 dark:text-slate-400">Extração dinâmica de atividades e confronto de boletos bancários.</p>
          </div>
        </div>

        {/* SELEÇÃO DE ABAS */}
        {companyCnpj && (
          <div className="flex gap-2 p-1 bg-slate-100 dark:bg-dark-bg rounded-xl mb-6">
            <button
              onClick={() => setActiveTab('logs')}
              className={`flex-1 py-2 px-4 rounded-lg text-sm font-bold transition-all ${
                activeTab === 'logs'
                  ? 'bg-white dark:bg-dark-surface shadow-sm text-primary-600 dark:text-primary-400'
                  : 'text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-300'
              }`}
            >
              📊 Relatórios de Atividades
            </button>
            <button
              onClick={() => setActiveTab('confront')}
              className={`flex-1 py-2 px-4 rounded-lg text-sm font-bold transition-all ${
                activeTab === 'confront'
                  ? 'bg-white dark:bg-dark-surface shadow-sm text-primary-600 dark:text-primary-400'
                  : 'text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-300'
              }`}
            >
              🔄 Confrontar PDF de Boletos
            </button>
          </div>
        )}

        {/* AVISO DE SEGURANÇA HTTP */}
        {window.location.protocol !== 'https:' && activeTab === 'logs' && (
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
        ) : activeTab === 'logs' ? (
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
                  <option value="Cobrancas_Diarias">📊 COBRANÇAS DIÁRIAS — OPERADOR + ANALU (COMPLETO)</option>
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
        ) : (
          /* ABA DE CONFRONTO */
          <div className="space-y-6">
            {!confrontResult ? (
              <form onSubmit={handleConfront} className="space-y-6">
                <div className="p-8 border-2 border-dashed border-slate-300 dark:border-dark-border rounded-2xl flex flex-col items-center justify-center bg-slate-50 dark:bg-dark-bg/30 text-center hover:bg-slate-100 dark:hover:bg-dark-bg/50 transition-colors">
                  <Upload className="text-slate-400 dark:text-slate-500 mb-4 animate-pulse" size={48} />
                  <p className="text-sm font-bold text-slate-700 dark:text-slate-300 mb-1">Arraste ou selecione o PDF do banco</p>
                  <p className="text-xs text-slate-400 dark:text-slate-500">Ex: Relatório Itaú "Consulta de boletos em aberto (vencidos)"</p>
                  
                  <input
                    type="file"
                    accept=".pdf"
                    required
                    onChange={e => setConfrontFile(e.target.files?.[0] || null)}
                    className="mt-6 text-xs text-slate-500 dark:text-slate-400 file:mr-4 file:py-2 file:px-4 file:rounded-xl file:border-0 file:text-xs file:font-semibold file:bg-primary-50 file:text-primary-700 file:hover:bg-primary-100 dark:file:bg-dark-surface dark:file:text-primary-400"
                  />
                </div>
                {confrontFile && (
                  <div className="flex items-center justify-between p-4 bg-slate-100 dark:bg-dark-bg/60 rounded-xl animate-fade-in">
                    <span className="text-xs font-semibold text-slate-600 dark:text-slate-300 max-w-[70%] truncate">
                      📄 {confrontFile.name}
                    </span>
                    <button type="submit" className="btn-primary py-2 px-6 text-xs">
                      Confrontar com Credos
                    </button>
                  </div>
                )}
              </form>
            ) : (
              /* TABELA DE RESULTADOS DO CONFRONTO */
              <div className="space-y-4 animate-fade-in">
                <div className="flex flex-col md:flex-row gap-4 items-center justify-between">
                  <div className="flex gap-4 w-full md:w-auto">
                    {/* Barra de Busca */}
                    <div className="relative flex-1 md:w-64">
                      <Search className="absolute left-3 top-3 text-slate-400 dark:text-slate-500" size={16} />
                      <input
                        type="text"
                        placeholder="Buscar cliente ou número..."
                        value={searchTerm}
                        onChange={e => setSearchTerm(e.target.value)}
                        className="input-field pl-9 py-2 text-xs"
                      />
                    </div>
                    {/* Filtro de Status */}
                    <select
                      value={statusFilter}
                      onChange={e => setStatusFilter(e.target.value)}
                      className="input-field py-2 text-xs md:w-44"
                    >
                      <option value="Todos">Todos os Status</option>
                      <option value="Pago">Pago / Baixado</option>
                      <option value="Aberto">Aberto</option>
                      <option value="Cartório">Cartório</option>
                      <option value="Negociado">Negociado</option>
                      <option value="Não Encontrado">Não Encontrado</option>
                    </select>
                  </div>

                  <div className="flex gap-2 w-full md:w-auto">
                    <button
                      onClick={() => { setConfrontResult(null); setConfrontFile(null); }}
                      className="btn-secondary py-2 px-4 text-xs w-full md:w-auto"
                    >
                      Voltar / Novo Envio
                    </button>
                    <button
                      onClick={handleExportConfront}
                      disabled={exporting}
                      className="btn-primary py-2 px-6 text-xs flex items-center justify-center gap-2 w-full md:w-auto"
                    >
                      <Download size={14} /> Exportar PDF
                    </button>
                  </div>
                </div>

                <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-dark-border">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead>
                      <tr className="bg-slate-50 dark:bg-dark-bg/60 text-slate-600 dark:text-slate-400 font-bold border-b border-slate-200 dark:border-dark-border">
                        {/* Render standard/most important headers to avoid clutter */}
                        {confrontResult.columns
                          .filter(col => {
                            const l = col.toLowerCase();
                            return l.includes('venc') || l.includes('seu') || l.includes('nosso') || l.includes('val') || l.includes('pag') || l.includes('sit') || l.includes('status');
                          })
                          .map((col, idx) => (
                            <th key={idx} className="p-3">{col}</th>
                          ))
                        }
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 dark:divide-dark-border/40">
                      {filteredRows.length === 0 ? (
                        <tr>
                          <td colSpan={confrontResult.columns.length} className="p-8 text-center text-slate-400 dark:text-slate-500 font-medium">
                            Nenhum registro encontrado com os filtros atuais.
                          </td>
                        </tr>
                      ) : (
                        filteredRows.map((row, rowIdx) => (
                          <tr key={rowIdx} className="hover:bg-slate-50/55 dark:hover:bg-dark-bg/25 transition-colors">
                            {confrontResult.columns
                              .filter(col => {
                                const l = col.toLowerCase();
                                return l.includes('venc') || l.includes('seu') || l.includes('nosso') || l.includes('val') || l.includes('pag') || l.includes('sit') || l.includes('status');
                              })
                              .map((col, colIdx) => {
                                const val = row[col] || '';
                                if (col === 'Status Credos') {
                                  let badgeClass = "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300";
                                  const valLower = val.toLowerCase();
                                  if (valLower === 'pago' || valLower === 'baixado') {
                                    badgeClass = "bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-400 dark:border-emerald-900/30";
                                  } else if (valLower === 'cartório' || valLower === 'cartorio' || valLower === 'protesto') {
                                    badgeClass = "bg-rose-50 text-rose-700 border border-rose-200 dark:bg-rose-950/40 dark:text-rose-400 dark:border-rose-900/30";
                                  } else if (valLower === 'aberto' || valLower === 'manter aberto') {
                                    badgeClass = "bg-amber-50 text-amber-700 border border-amber-200 dark:bg-amber-950/40 dark:text-amber-400 dark:border-amber-900/30";
                                  } else if (valLower === 'negociado') {
                                    badgeClass = "bg-indigo-50 text-indigo-700 border border-indigo-200 dark:bg-indigo-950/40 dark:text-indigo-400 dark:border-indigo-900/30";
                                  }
                                  return (
                                    <td key={colIdx} className="p-3">
                                      <span className={`px-2 py-1 rounded-lg text-[10px] font-black uppercase ${badgeClass}`}>
                                        {val}
                                      </span>
                                    </td>
                                  );
                                }
                                return (
                                  <td key={colIdx} className="p-3 text-slate-800 dark:text-slate-200">
                                    {val}
                                  </td>
                                );
                              })
                            }
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}

      </div>
    </Layout>
  );
};
