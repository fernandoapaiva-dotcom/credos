import React, { useState, useEffect } from 'react';
import { Layout } from '../components/ui/Layout';
import { useAuth, api } from '../context/AuthContext';
import { Save, RefreshCw, QrCode, PowerOff, Loader2, Sparkles, Upload, Image as ImageIcon, X, AlertTriangle, Play, Users } from 'lucide-react';

export const Settings: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'dados' | 'whatsapp' | 'email' | 'ia'>('dados');
  const [loading, setLoading] = useState(false);
  const [companyCnpj, setCompanyCnpj] = useState('');
  
  const [testingSMTP, setTestingSMTP] = useState(false);
  const [testingIMAP, setTestingIMAP] = useState(false);
  const [testingIA, setTestingIA] = useState(false);
  const [testingCert, setTestingCert] = useState(false);
  
  const [waCheckingStatus, setWaCheckingStatus] = useState(false);
  const [waGeneratingQr, setWaGeneratingQr] = useState(false);
  const [waDisconnecting, setWaDisconnecting] = useState(false);
  const [creatingGroup, setCreatingGroup] = useState(false);

  // Tab: Dados e Regras
  const [config, setConfig] = useState<any>({});
  
  // Tab: WhatsApp
  const [waStatus, setWaStatus] = useState<string>('desconhecido');
  const [waQrCode, setWaQrCode] = useState<string | null>(null);

  // Tab: IA
  const [scheduler, setScheduler] = useState<any>({ dias: [], hora: '09:00', ignorar_feriados: true, ativo: false });
  const [systemHalt, setSystemHalt] = useState(false);
  const [togglingHalt, setTogglingHalt] = useState(false);
  const [proactiveStatus, setProactiveStatus] = useState<any>({ total_documentos: 0 });
  const [indexingHistory, setIndexingHistory] = useState(false);

  const { updateCompanyLogo } = useAuth();

  useEffect(() => {
    const cnpj = localStorage.getItem('companyCnpj');
    if (cnpj) {
      setCompanyCnpj(cnpj);
      loadConfigs(cnpj);
      loadScheduler(cnpj);
      loadProactiveStatus(cnpj);
      loadSystemHalt();
      
      const checkInitialStatus = async () => {
        try {
          const res = await api.post(`/companies/${cnpj}/whatsapp/status`);
          setWaStatus(res.data.status);
        } catch (e) {
          setWaStatus('erro_conexao');
        }
      };
      checkInitialStatus();
    }
  }, []);

  const loadConfigs = async (cnpj: string) => {
    try {
      const res = await api.get(`/companies/${cnpj}/config`);
      setConfig(res.data);
    } catch (e) { }
  };

  const loadScheduler = async (cnpj: string) => {
    try {
      const res = await api.get(`/companies/${cnpj}/scheduler`);
      const s = res.data.scheduler;
      if (s) {
         setScheduler({
            dias: s.dias_ui || s.dias || [],
            hora: s.hora_envio || s.hora || '09:00',
            ignorar_feriados: s.ignorar_feriados ?? true,
            ativo: s.ativo ?? false
         });
      }
    } catch (e) { }
  };

  const loadProactiveStatus = async (cnpj: string) => {
    try {
      const res = await api.get(`/proactive/status/${cnpj}`);
      setProactiveStatus(res.data);
    } catch (e) { }
  };
  const loadSystemHalt = async () => {
    try {
      const res = await api.get('/companies/system/halt');
      setSystemHalt(res.data.halt);
    } catch (e) { }
  };

  const toggleSystemHalt = async () => {
    const action = systemHalt ? 'RETOMAR' : 'PARAR';
    if (!confirm(`Tem certeza que deseja ${action} todas as automações de todas as empresas?`)) return;
    
    setTogglingHalt(true);
    try {
       await api.post('/companies/system/halt', { halt: !systemHalt });
       setSystemHalt(!systemHalt);
       alert(`Sistema ${!systemHalt ? 'PAUSADO' : 'RETOMADO'} com sucesso!`);
    } catch (e) {
       alert('Erro ao alterar status de emergência.');
    }
    setTogglingHalt(false);
  };

  const handleIndexHistory = async () => {
    setIndexingHistory(true);
    try {
      await api.post(`/proactive/index-history/${companyCnpj}`);
      alert("Indexação histórica iniciada em segundo plano! A Analu está varrendo sua Caixa de Saída desde Outubro/2025.");
      setTimeout(() => loadProactiveStatus(companyCnpj), 5000);
    } catch (e: any) {
      alert(e.response?.data?.detail || "Erro ao iniciar indexação.");
    }
    setIndexingHistory(false);
  };

  const saveConfig = async () => {
    setLoading(true);
    try {
      await api.patch(`/companies/${companyCnpj}/config`, config);
      if (config.logo_b64) {
        updateCompanyLogo(config.logo_b64);
      }
      alert('Configurações salvas com sucesso!');
    } catch (e) {
      alert('Erro ao salvar');
    }
    setLoading(false);
  };

  const handleLogoUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onloadend = () => {
        setConfig({ ...config, logo_b64: reader.result as string });
      };
      reader.readAsDataURL(file);
    }
  };

  const handlePfxUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onloadend = () => {
        let base64 = reader.result as string;
        if (base64.includes(',')) base64 = base64.split(',')[1];
        setConfig({ ...config, cartorio_pfx_b64: base64 });
      };
      reader.readAsDataURL(file);
    }
  };

  const saveScheduler = async () => {
    setLoading(true);
    try {
      await api.patch(`/companies/${companyCnpj}/config`, { 
        gemini_api_key: config.gemini_api_key,
        cartorio_pfx_b64: config.cartorio_pfx_b64,
        cartorio_pfx_pass: config.cartorio_pfx_pass,
        cartorio_interval_min: config.cartorio_interval_min
      });
      await api.post(`/companies/${companyCnpj}/scheduler`, scheduler);
      alert('Cérebro IA e Agendamento salvos!');
    } catch (e) {
      alert('Erro ao salvar IA');
    }
    setLoading(false);
  };

  const testEmailSMTP = async () => {
    setTestingSMTP(true);
    try {
      await api.patch(`/companies/${companyCnpj}/config`, config);
      const res = await api.post(`/companies/${companyCnpj}/email/test`);
      alert(res.data.message);
    } catch (e: any) {
      alert(e.response?.data?.detail || 'Erro ao testar email de Envio (SMTP)');
    }
    setTestingSMTP(false);
  };

  const testEmailIMAP = async () => {
    setTestingIMAP(true);
    try {
      await api.patch(`/companies/${companyCnpj}/config`, config);
      const res = await api.post(`/companies/${companyCnpj}/email/test-imap`);
      alert(res.data.message);
    } catch (e: any) {
      alert(e.response?.data?.detail || 'Erro ao testar email de Recebimento (IMAP)');
    }
    setTestingIMAP(false);
  };

  const testCartorioCert = async () => {
    setTestingCert(true);
    try {
      await api.patch(`/companies/${companyCnpj}/config`, { 
        cartorio_pfx_b64: config.cartorio_pfx_b64,
        cartorio_pfx_pass: config.cartorio_pfx_pass
      });
      const res = await api.post(`/companies/${companyCnpj}/cartorio/test-cert`);
      alert(res.data.message);
    } catch (e: any) {
      alert(e.response?.data?.detail || 'Erro ao testar. Verifique se importou o arquivo corretamente e se a senha está certa.');
    }
    setTestingCert(false);
  };

  const testIA = async () => {
    setTestingIA(true);
    try {
      await api.patch(`/companies/${companyCnpj}/config`, { gemini_api_key: config.gemini_api_key });
      const res = await api.post(`/companies/${companyCnpj}/ai/test`);
      alert(res.data.message);
    } catch (e: any) {
      alert(e.response?.data?.detail || 'Erro ao testar Inteligência Artificial');
    }
    setTestingIA(false);
  };

  const checkIsLate = () => {
    const now = new Date();
    const currentDay = ['Domingo', 'Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado'][now.getDay()];
    const diasAtivos = scheduler.dias || scheduler.dias_ui || [];
    const isToday = Array.isArray(diasAtivos) && diasAtivos.includes(currentDay);
    const h = String(now.getHours()).padStart(2, '0');
    const m = String(now.getMinutes()).padStart(2, '0');
    const nowTimeString = `${h}:${m}`;
    const horaConfig = scheduler.hora || scheduler.hora_envio || "09:00";
    const isPastTime = nowTimeString > horaConfig;
    return isToday && isPastTime;
  };

  const isLate = checkIsLate();

  const handleTriggerLate = async () => {
     if (!confirm("Isso iniciará as cobranças de IA para todos os clientes pendentes agendados para hoje. Continuar?")) return;
     try {
       await api.post(`/companies/${companyCnpj}/ai/trigger`);
       alert("Disparo IA iniciado com sucesso em segundo plano! Clientes já cobrados hoje serão ignorados automaticamente.");
     } catch (e: any) {
       alert(e.response?.data?.detail || "Erro ao disparar IA manualmente.");
     }
  };

  const checkWaStatus = async () => {
    setWaCheckingStatus(true);
    try {
      const res = await api.post(`/companies/${companyCnpj}/whatsapp/status`);
      const status = res.data.status;
      setWaStatus(status);
      if (status === 'open' || status === 'connected') {
        alert('WhatsApp Conectado com sucesso! ✅');
      } else if (status === 'connecting') {
        alert('Status: Conectando / Aguardando leitura do QR Code ⏳');
      } else if (status === 'closed' || status === 'close' || status === 'disconnected') {
        alert('Status atual: Desconectado ❌ (Clique em "Gerar QR Code" para conectar)');
      } else {
        alert(`Status atual: ${status}`);
      }
    } catch (e) {
      setWaStatus('erro_conexao');
      alert('Houve um erro ao checar o status.');
    }
    setWaCheckingStatus(false);
  };

  const connectWa = async () => {
    setWaGeneratingQr(true);
    setWaQrCode(null);
    setWaStatus('connecting');
    try {
      const res = await api.post(`/companies/${companyCnpj}/whatsapp/create`);
      if (res.data?.qr_code_base64) {
        setWaQrCode(res.data.qr_code_base64);
      } else {
        fetchQrCode(15);
      }
    } catch (e: any) {
      alert(e.response?.data?.detail || 'Erro ao criar instância');
      setWaStatus('erro_conexao');
    }
    setWaGeneratingQr(false);
  };

  const fetchQrCode = async (retries = 15) => {
    try {
      const res = await api.get(`/companies/${companyCnpj}/whatsapp/qr`);
      if (res.data && res.data.qr_code_base64) {
        setWaQrCode(res.data.qr_code_base64);
        return;
      }
    } catch (e) {
      // Instance might be creating Baileys socket, retry
    }
    if (retries > 0) {
      setTimeout(() => fetchQrCode(retries - 1), 2000);
    }
  };

  const disconnectWa = async () => {
    setWaDisconnecting(true);
    try {
      await api.delete(`/companies/${companyCnpj}/whatsapp`);
      setWaStatus('closed');
      setWaQrCode(null);
      alert('WhatsApp Desconectado com sucesso.');
    } catch (e) { 
      alert('Erro ao desconectar.');
    }
    setWaDisconnecting(false);
  };

  const createReportGroup = async () => {
    setCreatingGroup(true);
    try {
      const res = await api.post(`/companies/${companyCnpj}/whatsapp/group/create`);
      alert(res.data.message);
      loadConfigs(companyCnpj);
    } catch (e: any) {
      alert(e.response?.data?.detail || "Erro ao criar grupo.");
    }
    setCreatingGroup(false);
  };

  return (
    <Layout title="Configurações">
      <div className="card max-w-5xl mx-auto">
        
        {/* Controle de Emergência Global - Sempre Visível no topo das configurações */}
        <div className="bg-red-50 dark:bg-red-900/20 border-b border-red-200 dark:border-red-800 p-4 flex items-center justify-between">
          <div>
            <h4 className="font-bold text-red-800 dark:text-red-400 flex items-center gap-2">
              <AlertTriangle size={18} /> CONTROLE DE EMERGÊNCIA (MASTER)
            </h4>
            <p className="text-xs text-red-700 dark:text-red-500">
              {systemHalt 
                ? '⚠️ O SISTEMA ESTÁ COMPLETAMENTE PAUSADO. Nenhuma cobrança automática será enviada.' 
                : 'O motor de automação está operando normalmente conforme agendamentos.'}
            </p>
          </div>
          <button 
            onClick={toggleSystemHalt}
            disabled={togglingHalt}
            className={`btn-primary border-none shadow-lg px-6 py-2 flex items-center gap-2 transition-all transform hover:scale-105 active:scale-95
              ${systemHalt ? 'bg-green-600 hover:bg-green-700' : 'bg-red-600 hover:bg-red-700'}`}
          >
            {togglingHalt ? <Loader2 className="animate-spin" size={20} /> : (systemHalt ? <Play size={20} /> : <PowerOff size={20} />)}
            {systemHalt ? 'RETOMAR SISTEMA' : 'PARAR TUDO (PÂNICO)'}
          </button>
        </div>

        <div className="flex border-b border-slate-200 dark:border-dark-border mb-6 overflow-x-auto">
          {['dados', 'whatsapp', 'email', 'ia'].map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab as any)}
              className={`px-4 py-3 font-medium text-sm transition-colors border-b-2 whitespace-nowrap
                ${activeTab === tab 
                  ? 'border-primary-500 text-primary-600 dark:text-primary-400' 
                  : 'border-transparent text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-300'}`}
            >
              {tab === 'dados' && '🏢 Dados & Regras CDC'}
              {tab === 'whatsapp' && '🟢 WhatsApp'}
              {tab === 'email' && '📧 E-mails'}
              {tab === 'ia' && '🤖 IA & Automação'}
            </button>
          ))}
        </div>

        {activeTab === 'dados' && (
          <div className="space-y-6 animate-fade-in">
            <h3 className="text-lg font-bold dark:text-white mb-4">Regras Financeiras</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div>
                <label className="block text-sm font-medium mb-1">Multa por Atraso (%)</label>
                <input 
                  type="number" step="0.5" 
                  className="input-field" 
                  value={config.multa_fixed || 2} 
                  onChange={e => setConfig({...config, multa_fixed: Number(e.target.value)})} 
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Juros Mensais (%)</label>
                <input 
                  type="number" step="0.1" 
                  className="input-field" 
                  value={config.juros_mensal || 1} 
                  onChange={e => setConfig({...config, juros_mensal: Number(e.target.value)})} 
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Dias p/ Cartório</label>
                <input 
                  type="number" 
                  className="input-field" 
                  value={config.dias_para_cartorio || 10} 
                  onChange={e => setConfig({...config, dias_para_cartorio: Number(e.target.value)})} 
                />
              </div>
            </div>
            
            <hr className="border-slate-200 dark:border-dark-border" />

            <h3 className="text-lg font-bold dark:text-white mb-4 mt-6">Cartões e Recebimentos PIX (Envio pela IA)</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pb-6">
              <div>
                <label className="block text-sm font-medium mb-1">Tipo de Chave PIX</label>
                <select 
                  className="input-field" 
                  value={config.tipo_chave_pix || 'CNPJ'} 
                  onChange={e => setConfig({...config, tipo_chave_pix: e.target.value})}
                >
                  <option value="CNPJ">CNPJ</option>
                  <option value="CPF">CPF</option>
                  <option value="Telefone">Telefone</option>
                  <option value="Email">E-mail</option>
                  <option value="Aleatória">Chave Aleatória</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Chave PIX Exata</label>
                <input 
                  type="text" 
                  className="input-field" 
                  value={config.chave_pix || ''} 
                  onChange={e => setConfig({...config, chave_pix: e.target.value})} 
                  placeholder="Ex: 54.804... etc"
                />
              </div>
            </div>

            {/* Item 8: Toggle PIX */}
            <div className={`flex items-center justify-between p-4 rounded-xl border-2 transition-all ${config.pix_habilitado !== 0 ? 'bg-green-50 border-green-200 dark:bg-green-900/15 dark:border-green-800' : 'bg-red-50 border-red-200 dark:bg-red-900/15 dark:border-red-800'}`}>
              <div>
                <h4 className={`font-bold text-sm flex items-center gap-2 ${config.pix_habilitado !== 0 ? 'text-green-800 dark:text-green-300' : 'text-red-700 dark:text-red-400'}`}>
                  💳 Habilitar Pagamento via PIX nas Cobranças
                </h4>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                  {config.pix_habilitado !== 0
                    ? 'A Analu inclui a chave PIX em todas as cobranças automáticas.'
                    : '⚠️ PIX desabilitado — clientes serão orientados a usar boleto bancário.'}
                </p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer ml-4 flex-shrink-0">
                <input
                  type="checkbox"
                  className="sr-only peer"
                  checked={config.pix_habilitado !== 0}
                  onChange={e => setConfig({...config, pix_habilitado: e.target.checked ? 1 : 0})}
                />
                <div className="w-11 h-6 bg-slate-200 peer-focus:outline-none rounded-full peer dark:bg-slate-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all dark:border-slate-600 peer-checked:bg-green-500"></div>
              </label>
            </div>

            
            <hr className="border-slate-200 dark:border-dark-border" />
            
            <h3 className="text-lg font-bold dark:text-white mb-4">Aparência e Marca (White-label)</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8 items-start">
               <div className="space-y-4">
                  <label className="block text-sm font-medium">Logotipo da Empresa</label>
                  <p className="text-xs text-slate-500 mb-4">Esta logo será exibida no Dashboard e no cabeçalho de todos os relatórios PDF.</p>
                  
                  <div className="flex items-center gap-4">
                     <label className="btn-secondary cursor-pointer">
                        <Upload size={18} className="mr-2" /> Escolher Imagem
                        <input type="file" className="hidden" accept="image/*" onChange={handleLogoUpload} />
                     </label>
                     {config.logo_b64 && (
                        <button 
                          onClick={() => setConfig({...config, logo_b64: ''})}
                          className="text-red-500 text-sm hover:underline flex items-center"
                        >
                          <X size={14} className="mr-1" /> Remover
                        </button>
                     )}
                  </div>
               </div>

               <div className="border-2 border-dashed border-slate-200 dark:border-dark-border rounded-xl p-6 flex flex-col items-center justify-center bg-white min-h-[140px] shadow-inner">
                  {config.logo_b64 ? (
                     <div className="relative group">
                        <img src={config.logo_b64} alt="Preview Logo" className="max-h-24 object-contain shadow-md rounded" />
                        <div className="mt-2 text-[10px] text-center text-slate-400 font-mono">Resolução Nativa</div>
                     </div>
                  ) : (
                     <div className="text-center text-slate-400">
                        <ImageIcon size={48} className="mx-auto mb-2 opacity-20" />
                        <p className="text-xs font-medium italic">Nenhuma logo carregada ainda</p>
                     </div>
                  )}
               </div>
            </div>

            <div className="flex justify-end pt-4">
              <button onClick={saveConfig} disabled={loading} className="btn-primary"><Save size={18} className="mr-2"/> Salvar Regras</button>
            </div>
          </div>
        )}

        {activeTab === 'whatsapp' && (
          <div className="space-y-6 animate-fade-in">
            <h3 className="text-lg font-bold dark:text-white mb-2">Conexão WhatsApp (Evolution API)</h3>
            <p className="text-sm text-slate-500 dark:text-slate-400 mb-6">Conecte o seu aparelho para que o robô possa enviar cobranças humanizadas via WhatsApp.</p>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-2">
              <div>
                <label className="block text-sm font-medium mb-1">Servidor Evolution URL</label>
                <input type="text" className="input-field" value={config.evo_url || ''} onChange={e => setConfig({...config, evo_url: e.target.value})} placeholder="Ex: https://api.empresa.com" />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Global API Key</label>
                <input type="password" className="input-field" value={config.evo_key || ''} onChange={e => setConfig({...config, evo_key: e.target.value})} placeholder="Sua chave global" />
              </div>
            </div>

            <div className="flex justify-end mb-4">
              <button onClick={saveConfig} disabled={loading} className="btn-primary py-2 px-4 shadow-sm text-sm"><Save size={16} className="mr-2"/> Gravar Chaves Evolution API</button>
            </div>

            <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 rounded-xl p-4 mb-6">
              <h4 className="font-semibold text-amber-800 dark:text-amber-300 mb-2">📱 Número do Operador (Notificações Internas)</h4>
              <p className="text-xs text-amber-700 dark:text-amber-400 mb-3">
                Este número receberá alertas quando um cliente enviar comprovante de pagamento e quando um título chegar ao prazo de cartório (20 dias). Inclua DDI+DDD (ex: 5561999999999).
              </p>
              <div className="flex gap-3">
                <input
                  type="text"
                  className="input-field flex-1"
                  value={config.operador_whatsapp || ''}
                  onChange={e => setConfig({...config, operador_whatsapp: e.target.value})}
                  placeholder="5561999999999"
                />
                <button onClick={saveConfig} disabled={loading} className="btn-primary whitespace-nowrap">
                  <Save size={16} className="mr-2"/>Salvar
                </button>
              </div>
            </div>
            
            <div className="bg-blue-50 dark:bg-blue-900/10 border border-blue-200 dark:border-blue-800 rounded-xl p-5 mb-6">
              <h4 className="font-bold text-blue-800 dark:text-blue-300 mb-3 flex items-center">
                <Users size={20} className="mr-2"/> 📈 Grupo de Relatórios (SaaS)
              </h4>
              <p className="text-sm text-blue-700 dark:text-blue-400 mb-4">
                Configure os números dos diretores que devem receber o relatório diário. 
                Ao clicar em gerar, a Analu criará um grupo privado no WhatsApp e adicionará essas pessoas.
              </p>
              
              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-blue-600 dark:text-blue-400 mb-1">Números dos Diretores (DDI+DDD+NÚMERO)</label>
                  <input
                    type="text"
                    className="input-field border-blue-200 focus:border-blue-400"
                    placeholder="Ex: 5561999999999 ; 5561888888888"
                    value={config.diretores_whatsapp || ''}
                    onChange={e => setConfig({...config, diretores_whatsapp: e.target.value})}
                  />
                  <p className="text-[10px] mt-1 text-blue-500">Separe os números por ponto e vírgula (;). O robô tentará adicionar todos.</p>
                </div>

                <div className="flex flex-col md:flex-row gap-4 items-end">
                  <div className="flex-1">
                    <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1">WhatsApp Group JID (ID do Grupo Gerado)</label>
                    <input
                      type="text"
                      className="input-field bg-slate-100 dark:bg-slate-800/50 cursor-not-allowed text-xs"
                      readOnly
                      value={config.grupo_relatorio_jid || 'Ainda não gerado'}
                    />
                  </div>
                  <button 
                    onClick={createReportGroup} 
                    disabled={creatingGroup || waStatus !== 'open'} 
                    className={`btn-primary px-6 h-[42px] shadow-lg shadow-blue-500/20 ${waStatus !== 'open' ? 'opacity-50 grayscale' : ''}`}
                  >
                    {creatingGroup ? <Loader2 className="animate-spin mr-2" size={18}/> : <Sparkles size={18} className="mr-2"/>}
                    {config.grupo_relatorio_jid ? 'Sincronizar Participantes' : 'Gerar Grupo Agora'}
                  </button>
                </div>
                {waStatus !== 'open' && (
                  <p className="text-xs text-red-500 font-medium italic">⚠️ Conecte o WhatsApp acima para habilitar a gestão de grupos.</p>
                )}
              </div>
            </div>

            <div className="bg-slate-50 dark:bg-dark-surface border border-slate-200 dark:border-dark-border rounded-xl p-6 flex flex-col md:flex-row items-center gap-6 mt-4">
              <div className="flex-1">
                <div className="text-sm font-medium text-slate-500 mb-1">Status da Conexão</div>
                
                {(waStatus === 'open' || waStatus === 'connected') && <div className="text-xl font-bold text-green-600">Conectado e Pronto ✅</div>}
                {waStatus === 'connecting' && <div className="text-xl font-bold text-amber-500">Aguardando QR Code... ⏳</div>}
                {(waStatus === 'closed' || waStatus === 'close' || waStatus === 'disconnected') && <div className="text-xl font-bold text-slate-600 dark:text-slate-400">Desconectado ❌</div>}
                {waStatus === 'desconhecido' && <div className="text-xl font-bold text-slate-400">Clique para verificar</div>}
                {waStatus === 'erro_conexao' && <div className="text-xl font-bold text-red-500">Erro na Evolution API</div>}
              </div>
              
              <div className="flex flex-col gap-2 w-full md:w-auto">
                <button onClick={checkWaStatus} disabled={waCheckingStatus || waGeneratingQr || waDisconnecting} className="btn-secondary whitespace-nowrap w-full justify-center">
                  {waCheckingStatus ? <Loader2 className="animate-spin mr-2" size={18}/> : <RefreshCw size={18} className="mr-2"/>} 
                  Checar Status
                </button>
                
                {(waStatus === 'open' || waStatus === 'connected' || waStatus === 'connecting' || waStatus === 'erro_conexao' || waStatus === 'desconhecido' || waStatus === 'closed' || waStatus === 'close' || waStatus === 'disconnected') && (
                  <button onClick={disconnectWa} disabled={waCheckingStatus || waGeneratingQr || waDisconnecting} className="btn-secondary text-red-600 hover:bg-red-50 border-red-200 mt-2 w-full justify-center">
                    {waDisconnecting ? <Loader2 className="animate-spin mr-2" size={18}/> : <PowerOff size={18} className="mr-2"/>}
                    Desconectar (Resetar Sessão)
                  </button>
                )}

                {(waStatus === 'closed' || waStatus === 'close' || waStatus === 'disconnected' || waStatus === 'desconhecido' || waStatus === 'erro_conexao' || waStatus === 'connecting') && (
                  <button onClick={connectWa} disabled={waCheckingStatus || waGeneratingQr || waDisconnecting} className="btn-primary whitespace-nowrap mt-2 w-full justify-center">
                    {waGeneratingQr ? <Loader2 className="animate-spin mr-2" size={18}/> : <QrCode size={18} className="mr-2"/>}
                    Gerar QR Code
                  </button>
                )}
              </div>
            </div>

            {waStatus === 'connecting' && !waQrCode && (
              <div className="flex flex-col items-center justify-center p-8 border-2 border-dashed border-amber-400/40 bg-amber-500/5 rounded-xl mt-6">
                <Loader2 className="animate-spin text-amber-500 mb-3" size={36} />
                <p className="text-sm font-medium text-amber-600 dark:text-amber-400">Gerando QR Code com a Evolution API... Aguarde alguns segundos.</p>
              </div>
            )}

            {waQrCode && waStatus !== 'open' && waStatus !== 'connected' && (
              <div className="flex flex-col items-center justify-center p-8 border-2 border-dashed border-slate-300 dark:border-dark-border rounded-xl mt-6">
                 <img src={waQrCode} alt="WhatsApp QR Code" className="w-64 h-64 border-4 border-white shadow-lg rounded-lg mb-4" />
                 <p className="text-sm text-slate-500">Abra o WhatsApp no celular, vá em Aparelhos Conectados e escaneie este código.</p>
                 <button onClick={checkWaStatus} className="btn-secondary mt-4">Já escaneei (Atualizar Status)</button>
              </div>
            )}
          </div>
        )}

        {activeTab === 'email' && (
          <div className="space-y-6 animate-fade-in">
             <h3 className="text-lg font-bold dark:text-white mb-2">Servidores e Contas de E-mail</h3>
             
             <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
                <div>
                  <label className="block text-sm font-medium mb-1">Servidor IMAP (Receber)</label>
                  <input type="text" className="input-field" value={config.imap_server || ''} onChange={e => setConfig({...config, imap_server: e.target.value})} placeholder="imap.gmail.com" />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">Servidor SMTP (Enviar)</label>
                  <input type="text" className="input-field" value={config.smtp_server || ''} onChange={e => setConfig({...config, smtp_server: e.target.value})} placeholder="smtp.gmail.com" />
                </div>
             </div>

             <div className="grid grid-cols-1 md:grid-cols-2 gap-6 bg-slate-50 dark:bg-dark-surface p-6 rounded-xl border border-slate-200 dark:border-dark-border">
                <div className="space-y-4 border-r-0 md:border-r border-slate-200 dark:border-dark-border md:pr-6">
                  <h4 className="font-bold text-slate-800 dark:text-slate-200">Email Base (Leitura de PDF)</h4>
                  <div>
                    <label className="block text-xs font-medium mb-1">Usuário / Endereço</label>
                    <input type="text" className="input-field" value={config.base_mail_user || ''} onChange={e => setConfig({...config, base_mail_user: e.target.value})} />
                  </div>
                  <div>
                    <label className="block text-xs font-medium mb-1">Senha (App Password)</label>
                    <input type="password" className="input-field" value={config.base_mail_pass || ''} onChange={e => setConfig({...config, base_mail_pass: e.target.value})} />
                  </div>
                </div>
                
                <div className="space-y-4 md:pl-2">
                  <h4 className="font-bold text-slate-800 dark:text-slate-200">Email Financeiro (Envio de Cobranças)</h4>
                  <div>
                    <label className="block text-xs font-medium mb-1">Usuário / Endereço</label>
                    <input type="text" className="input-field" value={config.fin_mail_user || ''} onChange={e => setConfig({...config, fin_mail_user: e.target.value})} />
                  </div>
                  <div>
                    <label className="block text-xs font-medium mb-1">Senha (App Password)</label>
                    <input type="password" className="input-field" value={config.fin_mail_pass || ''} onChange={e => setConfig({...config, fin_mail_pass: e.target.value})} />
                  </div>
                </div>
             </div>

             <div className="flex justify-end pt-4 gap-3">
              <button onClick={testEmailIMAP} disabled={testingIMAP} className="btn-secondary">
                {testingIMAP && <Loader2 className="animate-spin mr-2" size={18} />} Testar Recebimento (IMAP)
              </button>
              <button onClick={testEmailSMTP} disabled={testingSMTP} className="btn-secondary">
                {testingSMTP && <Loader2 className="animate-spin mr-2" size={18} />} Testar Envio (SMTP)
              </button>
              <button onClick={saveConfig} disabled={loading} className="btn-primary">
                {loading ? <Loader2 className="animate-spin mr-2" size={18} /> : <Save size={18} className="mr-2"/>} Salvar E-mails
              </button>
            </div>
          </div>
        )}

        {activeTab === 'ia' && (
          <div className="space-y-6 animate-fade-in">

             <h3 className="text-lg font-bold dark:text-white mb-2">🤖 Cérebro e Robô Agendador</h3>
             <p className="text-sm text-slate-500 mb-6">Configure a inteligência do sistema e os horários de disparo automático.</p>
             
             <div className="mb-6">
                <label className="block text-sm font-medium mb-1">API Key (Google Gemini)</label>
                <input 
                  type="password" 
                  className="input-field max-w-lg" 
                  value={config.gemini_api_key || ''} 
                  onChange={e => setConfig({...config, gemini_api_key: e.target.value})} 
                  placeholder="AIzaSy..."
                />
             </div>

             <div className="bg-white dark:bg-dark-surface p-6 rounded-xl border border-slate-200 dark:border-dark-border mb-6">
                <h4 className="font-bold text-slate-800 dark:text-white mb-4 flex items-center gap-2">
                   🏛️ Configurações de Cartório (Robô Playwright)
                </h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                   <div className="space-y-4">
                      <div>
                         <label className="block text-sm font-medium mb-1">Certificado Digital A1 (.pfx)</label>
                         <div className="flex items-center gap-3">
                            <label className="btn-secondary py-1.5 px-3 text-xs cursor-pointer">
                               <Upload size={14} className="mr-2" /> {config.cartorio_pfx_b64 ? 'Alterar Certificado' : 'Selecionar .pfx'}
                               <input type="file" className="hidden" accept=".pfx,.p12" onChange={handlePfxUpload} />
                            </label>
                            {config.cartorio_pfx_b64 && <span className="text-xs text-green-500 font-medium">Carregado ✅</span>}
                         </div>
                      </div>
                       <div>
                         <label className="block text-sm font-medium mb-1">Senha do Certificado</label>
                         <div className="flex gap-2">
                           <input 
                             type="password" 
                             className="input-field" 
                             value={config.cartorio_pfx_pass || ''} 
                             onChange={e => setConfig({...config, cartorio_pfx_pass: e.target.value})} 
                           />
                           <button 
                             onClick={testCartorioCert}
                             disabled={testingCert}
                             className="btn-secondary whitespace-nowrap"
                           >
                             {testingCert ? <Loader2 className="animate-spin" size={16} /> : "Testar Validade"}
                           </button>
                         </div>
                      </div>
                   </div>
                   <div className="space-y-4">
                      <div>
                         <label className="block text-sm font-medium mb-1">Intervalo entre Envios (minutos)</label>
                         <input 
                           type="number" 
                           className="input-field w-32" 
                           value={config.cartorio_interval_min || 5} 
                           onChange={e => setConfig({...config, cartorio_interval_min: Number(e.target.value)})} 
                         />
                         <p className="text-[10px] text-slate-500 mt-1">Recomendado: 5 a 10 minutos para evitar bloqueios.</p>
                      </div>
                   </div>
                </div>
             </div>

             <div className="bg-slate-50 dark:bg-dark-surface p-6 rounded-xl border border-slate-200 dark:border-dark-border mb-6">
                <div className="flex items-center justify-between mb-6">
                  <h4 className="font-bold text-slate-800 dark:text-white">Robô de Automação Diária</h4>
                  <div className="flex items-center gap-4">
                     <button 
                       onClick={handleTriggerLate}
                       title="Força o início do robô agora mesmo para os títulos de hoje"
                       className="text-xs flex items-center gap-1 bg-amber-100 hover:bg-amber-200 text-amber-800 px-3 py-1.5 rounded-lg border border-amber-300 transition-all dark:bg-amber-900/40 dark:text-amber-300 dark:border-amber-700 font-bold"
                     >
                        🚀 Forçar Envio Hoje {isLate ? '(Atrasado)' : ''}
                     </button>
                     <label className="relative inline-flex items-center cursor-pointer">
                        <input type="checkbox" className="sr-only peer" checked={scheduler.ativo} onChange={e => setScheduler({...scheduler, ativo: e.target.checked})} />
                        <div className="w-11 h-6 bg-slate-200 peer-focus:outline-none rounded-full peer dark:bg-slate-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all dark:border-slate-600 peer-checked:bg-primary-600"></div>
                     </label>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <label className="block text-sm font-medium mb-2">Dias da Semana</label>
                    <div className="flex flex-wrap gap-2">
                       {['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo'].map(dia => (
                         <button 
                           key={dia}
                           onClick={() => {
                              const list = scheduler.dias || [];
                              if (list.includes(dia)) {
                                setScheduler({...scheduler, dias: list.filter((d:string) => d !== dia)});
                              } else {
                                setScheduler({...scheduler, dias: [...list, dia]});
                              }
                           }}
                           className={`px-3 py-1.5 text-xs font-medium rounded-full border transition-colors ${
                              (scheduler.dias || []).includes(dia) 
                                ? 'bg-primary-100 text-primary-700 border-primary-300 dark:bg-primary-900/40 dark:text-primary-400 dark:border-primary-700' 
                                : 'bg-white text-slate-500 border-slate-200 dark:bg-dark-bg dark:text-slate-400 dark:border-slate-700'
                           }`}
                         >
                           {dia}
                         </button>
                       ))}
                    </div>
                  </div>

                  <div className="space-y-4">
                    <div>
                      <label className="block text-sm font-medium mb-1">Horário de Disparo</label>
                      <input type="time" className="input-field w-32" value={scheduler.hora} onChange={e => setScheduler({...scheduler, hora: e.target.value})} />
                    </div>
                    <div>
                       <label className="flex items-center text-sm text-slate-700 dark:text-slate-300 cursor-pointer">
                         <input type="checkbox" className="mr-2 w-4 h-4 rounded text-primary-600" checked={scheduler.ignorar_feriados} onChange={e => setScheduler({...scheduler, ignorar_feriados: e.target.checked})} />
                         Pausar robô em Feriados Nacionais
                       </label>
                    </div>
                  </div>
                </div>
             </div>

             <div className="flex justify-end pt-4 gap-3">
              <button onClick={testIA} disabled={testingIA} className="btn-secondary group">
                {testingIA ? (
                  <Sparkles className="animate-spin text-amber-500 mr-2" size={18}/>
                ) : (
                  <Sparkles size={18} className="mr-2 group-hover:text-amber-500 group-hover:animate-pulse transition-colors" />
                )}
                Testar Conexão Inteligência Artificial
              </button>
              <button onClick={saveScheduler} disabled={loading} className="btn-primary">
                 {loading ? <Loader2 className="animate-spin mr-2" size={18} /> : <Save size={18} className="mr-2"/>} Salvar Automação e IA
               </button>
             </div>

             <hr className="border-slate-200 dark:border-dark-border my-8" />

             <div className="bg-primary-50 dark:bg-primary-900/10 p-6 rounded-xl border border-primary-200 dark:border-primary-800/50">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h4 className="font-bold text-primary-900 dark:text-primary-300 flex items-center gap-2">
                       📡 Monitoramento Proativo (SoftSystem / Caixa de Saída)
                    </h4>
                    <p className="text-xs text-primary-700 dark:text-primary-400 mt-1">
                      A Analu captura faturas e boletos enviados pelo seu SoftSystem para garantir consultas instantâneas.
                    </p>
                  </div>
                  <div className="text-center bg-white dark:bg-primary-900/40 px-4 py-2 rounded-lg border border-primary-200 dark:border-primary-800 shadow-sm">
                     <div className="text-2xl font-black text-primary-600 dark:text-primary-400">{proactiveStatus.total_documentos}</div>
                     <div className="text-[10px] uppercase tracking-wider font-bold text-slate-400">Faturas Indexadas</div>
                  </div>
                </div>

                <div className="flex flex-col sm:flex-row items-center gap-4 mt-6">
                   <button 
                     onClick={handleIndexHistory}
                     disabled={indexingHistory}
                     className="btn-primary w-full sm:w-auto bg-primary-600 hover:bg-primary-700"
                   >
                      {indexingHistory ? <Loader2 className="animate-spin mr-2" size={18}/> : <RefreshCw size={18} className="mr-2"/>}
                      Indexar Histórico (desde Out/2025)
                   </button>
                   <p className="text-[10px] text-slate-500 dark:text-slate-400 italic">
                      💡 Recomendado rodar uma vez para preencher o repositório com títulos antigos.
                   </p>
                </div>
             </div>
          </div>
        )}

      </div>
    </Layout>
  );
};
