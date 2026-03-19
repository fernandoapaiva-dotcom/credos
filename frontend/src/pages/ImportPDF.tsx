import React, { useState, useEffect } from 'react';
import { Layout } from '../components/ui/Layout';
import { api } from '../context/AuthContext';
import { UploadCloud, CheckCircle2, AlertTriangle, ArrowRight, PlusCircle, Trash2, Eye } from 'lucide-react';

interface LayoutData {
  id: number;
  nome_layout: string;
  col_vencimento: string;
  col_numero: string;
  col_valor: string;
  col_pagador: string;
}

interface TitlePreview {
  pagador: string;
  numero: string;
  vencimento: string;
  valor: number;
}

interface DBTitle {
  id: number;
  pagador: string;
  numero_nf: string;
  vencimento: string;
  valor: number;
  status: string;
}

export const ImportPDF: React.FC = () => {
  const [file, setFile] = useState<File | null>(null);
  const [layouts, setLayouts] = useState<LayoutData[]>([]);
  const [selectedLayoutId, setSelectedLayoutId] = useState<string>('');
  
  const [preview, setPreview] = useState<TitlePreview[]>([]);
  const [novosClientes, setNovosClientes] = useState<string[]>([]);
  const [missingTitles, setMissingTitles] = useState<DBTitle[]>([]);
  
  // States for New Layout Mapping
  const [isMapping, setIsMapping] = useState(false);
  const [pdfHeaders, setPdfHeaders] = useState<string[]>([]);
  const [pdfSample, setPdfSample] = useState<any[]>([]);
  const [newLayoutName, setNewLayoutName] = useState('');
  const [mapVencimento, setMapVencimento] = useState('');
  const [mapNumero, setMapNumero] = useState('');
  const [mapValor, setMapValor] = useState('');
  const [mapPagador, setMapPagador] = useState('');

  const [loading, setLoading] = useState(false);
  const [step, setStep] = useState(1);

  useEffect(() => {
    fetchLayouts();
  }, []);

  const fetchLayouts = async () => {
    try {
      const res = await api.get('/import/layouts');
      setLayouts(res.data.layouts || []);
      if (res.data.layouts && res.data.layouts.length > 0) {
        setSelectedLayoutId(String(res.data.layouts[0].id));
      } else {
        setSelectedLayoutId('new');
      }
    } catch(e) { }
  };

  const deleteLayout = async (id: number) => {
    if (!window.confirm("Deseja realmente excluir este layout?")) return;
    try {
      await api.delete(`/import/layouts/${id}`);
      fetchLayouts();
    } catch(e) {
      alert("Erro ao excluir layout.");
    }
  };

  const handlePreviewMap = async () => {
    if (!file) return;
    setLoading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await api.post('/import/preview-pdf', formData);
      setPdfHeaders(res.data.headers);
      setPdfSample(res.data.sample);
      setIsMapping(true);
    } catch (err: any) {
      alert("Erro ao ler PDF: " + (err.response?.data?.detail || err.message));
    }
    setLoading(false);
  };

  const saveLayoutAndProceed = async () => {
    if (!newLayoutName || !mapVencimento || !mapNumero || !mapValor || !mapPagador) {
      alert("Preencha o nome do layout e mapeie todas as colunas.");
      return;
    }
    setLoading(true);
    try {
      const novoLayout = {
        nome_layout: newLayoutName,
        col_vencimento: mapVencimento,
        col_numero: mapNumero,
        col_valor: mapValor,
        col_pagador: mapPagador
      };
      await api.post('/import/layouts', novoLayout);
      await fetchLayouts();
      
      // Encontrar o ID do layout recém criado usando o nome (já que fetchLayouts vai rodar e recarregar os items)
      // Para ser rapido, submetemos a importacao mandando o JSON gerado
      await processUploadWithLayout(novoLayout);
    } catch(err) {
      alert("Erro ao salvar layout.");
    }
    setLoading(false);
  };

  const handleUpload = async () => {
    if (selectedLayoutId === 'new') {
      handlePreviewMap();
    } else {
      const layoutCfg = layouts.find(l => String(l.id) === selectedLayoutId);
      if (layoutCfg) {
        await processUploadWithLayout(layoutCfg);
      }
    }
  };

  const processUploadWithLayout = async (layoutCfg: any) => {
    setLoading(true);
    try {
      const resOpen = await api.get('/crm/titles?status=Aberto');
      const openTitles: DBTitle[] = resOpen.data.titles || [];

      const formData = new FormData();
      formData.append('file', file as Blob);
      formData.append('layout', JSON.stringify(layoutCfg));

      const resUpload = await api.post('/import/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });

      const readTitles: TitlePreview[] = resUpload.data.titulos;
      
      const missing = openTitles.filter(dbT => 
        !readTitles.some(pdfT => String(pdfT.numero) === String(dbT.numero_nf) && pdfT.pagador === dbT.pagador)
      );

      setPreview(readTitles);
      setNovosClientes(resUpload.data.novos_clientes_necessarios);
      setMissingTitles(missing.map(m => ({...m, action: 'Cartório'}))); 
      setIsMapping(false);
      setStep(2);
    } catch(err: any) {
      alert("Erro ao processar o PDF. " + (err.response?.data?.detail || err.message));
    }
    setLoading(false);
  };

  const handleConfirm = async () => {
    setLoading(true);
    try {
      for (const nc of novosClientes) {
        await api.post('/crm/clients', { nome: nc, cnpj: '00000000000000', whatsapp: '', email: '', contato: '' });
      }

      await api.post('/import/confirm', { titulos: preview });

      for (const mt of missingTitles) {
        const action = (mt as any).action || 'Cartório';
        await api.patch(`/crm/titles/${mt.id}`, { status: action, acao: 'Pausar' });
      }

      alert("Importação e atualizações concluídas com sucesso!");
      setStep(1);
      setFile(null);
      setPreview([]);
    } catch(err) {
      alert("Erro ao salvar.");
    }
    setLoading(false);
  };

  return (
    <Layout title="Importar Relatório de Retorno (PDF)">
      <div className="card max-w-4xl mx-auto">
        
        {step === 1 && !isMapping && (
          <div className="space-y-6 animate-fade-in">
            <h2 className="text-xl font-bold dark:text-white mb-2">Novo Lote</h2>
            
            <div className="bg-slate-50 dark:bg-dark-surface p-4 rounded-xl border border-slate-200 dark:border-dark-border mb-6">
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">Selecione o Layout do Banco</label>
              <div className="flex gap-2">
                <select 
                  className="input-field flex-1"
                  value={selectedLayoutId}
                  onChange={e => setSelectedLayoutId(e.target.value)}
                >
                  <option value="new">➕ Mapear Novo Layout de Banco</option>
                  {layouts.map(l => (
                    <option key={l.id} value={l.id}>{l.nome_layout}</option>
                  ))}
                </select>
                {selectedLayoutId !== 'new' && (
                  <button onClick={() => deleteLayout(Number(selectedLayoutId))} className="px-3 py-2 bg-red-100 text-red-600 rounded-lg hover:bg-red-200" title="Excluir Layout">
                    <Trash2 size={20} />
                  </button>
                )}
              </div>
            </div>

            <div 
              className="border-2 border-dashed border-slate-300 dark:border-dark-border rounded-xl p-12 flex flex-col items-center justify-center bg-slate-50 hover:bg-slate-100 dark:bg-dark-bg/50 dark:hover:bg-dark-surface cursor-pointer ring-primary-500 transition-all"
              onClick={() => document.getElementById('pdf-upload')?.click()}
            >
              <UploadCloud size={48} className="text-primary-500 mb-4" />
              <p className="text-slate-700 dark:text-slate-300 font-medium text-center">
                {file ? file.name : "Clique ou arraste o PDF gerado pelo banco para iniciar"}
              </p>
              <input id="pdf-upload" type="file" accept=".pdf" className="hidden" onChange={e => setFile(e.target.files?.[0] || null)} />
            </div>

            <div className="flex justify-end">
              <button onClick={handleUpload} disabled={!file || loading} className="btn-primary py-2.5 px-6">
                {loading ? 'Processando...' : selectedLayoutId === 'new' ? 'Mapear Colunas do Arquivo →' : 'Analisar e Importar Títulos →'}
              </button>
            </div>
          </div>
        )}

        {/* STEP 1.5 - MAPPING */}
        {isMapping && (
          <div className="space-y-6 animate-fade-in">
            <h2 className="text-xl font-bold dark:text-white flex items-center gap-2"><Eye className="text-primary-500"/> Mapeamento de Layout</h2>
            <p className="text-slate-500 dark:text-slate-400">Identificamos as seguintes colunas no documento. Por favor, indique qual é qual para que o sistema aprenda e faça sozinho da próxima vez.</p>
            
            <div className="bg-slate-50 dark:bg-dark-bg p-4 rounded-xl border border-slate-200 dark:border-dark-border overflow-x-auto text-sm mb-6">
               <p className="font-semibold mb-2">Amostra dos Dados no PDF:</p>
               <table className="w-full min-w-[600px] text-left">
                 <thead>
                   <tr>
                     {pdfHeaders.map(h => <th key={h} className="p-2 border-b dark:border-slate-700">{h}</th>)}
                   </tr>
                 </thead>
                 <tbody>
                   {pdfSample.map((row, i) => (
                     <tr key={i}>
                       {pdfHeaders.map(h => <td key={h} className="p-2 border-b dark:border-slate-800 text-slate-500">{row[h]}</td>)}
                     </tr>
                   ))}
                 </tbody>
               </table>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-1">Coluna de Vencimento</label>
                <select className="input-field" value={mapVencimento} onChange={e => setMapVencimento(e.target.value)}>
                  <option value="">-- Selecione --</option>
                  {pdfHeaders.map(h => <option key={h} value={h}>{h}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Coluna do Nosso Número (NF)</label>
                <select className="input-field" value={mapNumero} onChange={e => setMapNumero(e.target.value)}>
                  <option value="">-- Selecione --</option>
                  {pdfHeaders.map(h => <option key={h} value={h}>{h}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Coluna de Valor</label>
                <select className="input-field" value={mapValor} onChange={e => setMapValor(e.target.value)}>
                  <option value="">-- Selecione --</option>
                  {pdfHeaders.map(h => <option key={h} value={h}>{h}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Coluna do Pagador (Cliente)</label>
                <select className="input-field" value={mapPagador} onChange={e => setMapPagador(e.target.value)}>
                  <option value="">-- Selecione --</option>
                  {pdfHeaders.map(h => <option key={h} value={h}>{h}</option>)}
                </select>
              </div>
            </div>

            <div className="mt-6 pt-6 border-t border-slate-200 dark:border-dark-border">
              <label className="block text-sm font-bold mb-1">Dê um nome a este modelo (Ex: Retorno Bradesco)</label>
              <input 
                type="text" 
                className="input-field max-w-sm" 
                placeholder="Nome do Banco/Layout" 
                value={newLayoutName} 
                onChange={e => setNewLayoutName(e.target.value)} 
              />
            </div>

            <div className="flex justify-end gap-3 mt-8">
              <button onClick={() => setIsMapping(false)} className="btn-secondary">Voltar</button>
              <button onClick={saveLayoutAndProceed} disabled={loading} className="btn-primary">
                {loading ? 'Salvando...' : 'Salvar Layout e Importar'}
              </button>
            </div>
          </div>
        )}

        {/* STEP 2 - RESULTS SHOWCASE */}
        {step === 2 && (
          <div className="space-y-8 animate-slide-up">
            <div>
              <h2 className="text-xl font-bold dark:text-white flex items-center"><CheckCircle2 className="text-green-500 mr-2"/> Leitura Concluída e Inteligência Aplicada</h2>
              <p className="text-slate-500 dark:text-slate-400">Foram identificados {preview.length} títulos no documento.</p>
            </div>

            {novosClientes.length > 0 && (
               <div className="p-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
                 <h4 className="font-bold text-blue-800 dark:text-blue-300 mb-2">Novos Clientes Identificados</h4>
                 <ul className="list-disc pl-5 text-sm text-blue-700 dark:text-blue-400">
                   {novosClientes.map(c => <li key={c}>{c}</li>)}
                 </ul>
                 <p className="text-xs mt-2 text-blue-600 dark:text-blue-500">O sistema criará o cadastro base deles (Nome). Preencha CNPJ e Contatos no Menu CRM posteriormente.</p>
               </div>
            )}

            {missingTitles.length > 0 && (
              <div className="p-5 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-xl">
                <h4 className="font-bold text-amber-800 dark:text-amber-300 mb-2 flex items-center">
                  <AlertTriangle className="mr-2" size={20} /> Conciliação Inteligente: Títulos Desaparecidos
                </h4>
                <p className="text-sm text-amber-700 dark:text-amber-400 mb-4">Os títulos abaixo constavam como "Abertos" no banco de dados para os seus clientes, mas <strong>não retornaram</strong> neste novo PDF. Se não retornaram, provavelmente mudaram de status (Foram Pagos ou Para Cartório). Diga-me o que fazer com eles:</p>
                
                <div className="space-y-3">
                  {missingTitles.map((mt, idx) => (
                    <div key={mt.id} className="flex flex-col sm:flex-row sm:items-center justify-between p-3 bg-white dark:bg-dark-surface rounded-lg border border-amber-100 dark:border-amber-700 gap-4">
                      <div className="text-sm dark:text-slate-300 flex-1">
                        <strong className="block text-slate-800 dark:text-white">{mt.pagador}</strong>
                        NF: {mt.numero_nf} - R$ {Number(mt.valor).toLocaleString('pt-BR', {minimumFractionDigits:2})}
                      </div>
                      <select 
                        className="input-field py-1.5 text-sm w-full sm:w-64"
                        value={(mt as any).action}
                        onChange={(e) => {
                          const newMissing = [...missingTitles];
                          (newMissing[idx] as any).action = e.target.value;
                          setMissingTitles(newMissing);
                        }}
                      >
                        <option value="Pago">Marcar como Pago</option>
                        <option value="Cartório">Encaminhado p/ Cartório</option>
                        <option value="Cancelado">Foi Cancelado pelo Emissor</option>
                      </select>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="flex justify-end gap-3 pt-4 border-t border-slate-200 dark:border-dark-border">
              <button onClick={() => setStep(1)} className="btn-secondary">Cancelar</button>
              <button onClick={handleConfirm} disabled={loading} className="btn-primary px-8">
                {loading ? 'Salvando na Base...' : 'Aplicar Tudo na Base de Dados'}
              </button>
            </div>

            <div className="mt-8 pt-8">
              <h3 className="font-bold mb-4 dark:text-white">Prévia Detalhada dos Títulos Encontrados</h3>
              <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-dark-border">
                <table className="w-full text-sm text-left">
                  <thead className="bg-slate-50 dark:bg-dark-surface dark:text-slate-300">
                    <tr>
                      <th className="p-3">Pagador</th>
                      <th className="p-3">Número NF</th>
                      <th className="p-3">Vencimento</th>
                      <th className="p-3 text-right">Valor</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.map((p, i) => (
                      <tr key={i} className="border-t border-slate-200 dark:border-dark-border">
                        <td className="p-3">{p.pagador}</td>
                        <td className="p-3">{p.numero}</td>
                        <td className="p-3">{p.vencimento}</td>
                        <td className="p-3 text-right font-medium text-slate-700 dark:text-slate-300">R$ {Number(p.valor).toLocaleString('pt-BR', {minimumFractionDigits:2})}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

          </div>
        )}
      </div>
    </Layout>
  );
};
