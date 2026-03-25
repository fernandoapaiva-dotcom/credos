import React, { useState, useEffect } from 'react';
import { Layout } from '../components/ui/Layout';
import { useAuth, api } from '../context/AuthContext';
import { Save, RefreshCw, QrCode, PowerOff, Loader2, Sparkles, Upload, Image as ImageIcon, X } from 'lucide-react';

export const Settings: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'dados' | 'whatsapp' | 'email' | 'ia'>('dados');
  const [loading, setLoading] = useState(false);
  const [companyCnpj, setCompanyCnpj] = useState('');
  
  const [testingSMTP, setTestingSMTP] = useState(false);
  const [testingIMAP, setTestingIMAP] = useState(false);
  const [testingIA, setTestingIA] = useState(false);
  
  const [waCheckingStatus, setWaCheckingStatus] = useState(false);
  const [waGeneratingQr, setWaGeneratingQr] = useState(false);
  const [waDisconnecting, setWaDisconnecting] = useState(false);

  // Tab: Dados e Regras
  const [config, setConfig] = useState<any>({});
  
  // Tab: WhatsApp
  const [waStatus, setWaStatus] = useState<string>('desconhecido');
  const [waQrCode, setWaQrCode] = useState<string | null>(null);

  // Tab: IA
  const [scheduler, setScheduler] = useState<any>({ dias: [], hora: '09:00', ignorar_feriados: true, ativo: false });

  const { updateCompanyLogo } = useAuth();

  useEffect(() => {
    // Read the current selected company from local storage implicitly or state
    const cnpj = localStorage.getItem('companyCnpj');
    if (cnpj) {
      setCompanyCnpj(cnpj);
      loadConfigs(cnpj);
      loadScheduler(cnpj);
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
      setScheduler(res.data.scheduler || { dias: [], hora: '09:00', ignorar_feriados: true, ativo: false });
    } catch (e) { }
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

  const saveScheduler = async () => {
    setLoading(true);
    try {
      await api.patch(`/companies/${companyCnpj}/config`, { gemini_api_key: config.gemini_api_key });
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

  // --- WhatsApp Evolution ---
  const checkWaStatus = async () => {
    setWaCheckingStatus(true);
    try {
      const res = await api.post(`/companies/${companyCnpj}/whatsapp/status`);
      setWaStatus(res.data.status);
      alert(res.data.status === 'open' ? 'WhatsApp Conectado!' : `Status atual: ${res.data.status}`);
    } catch (e) {
      setWaStatus('erro_conexao');
      alert('Houve um erro ao checar o status.');
    }
    setWaCheckingStatus(false);
  };

  const connectWa = async () => {
    setWaGeneratingQr(true);
    try {
      await api.post(`/companies/${companyCnpj}/whatsapp/create`);
      setWaStatus('connecting');
      fetchQrCode();
    } catch (e: any) {
      alert(e.response?.data?.detail || 'Erro ao criar instância');
    }
    setWaGeneratingQr(false);
  };

  const fetchQrCode = async () => {
    try {
      const res = await api.get(`/companies/${companyCnpj}/whatsapp/qr`);
      setWaQrCode(res.data.qr_code_base64);
    } catch (e) {
      setTimeout(fetchQrCode, 3000); // Tentar de novo
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

  return (
    <Layout title="Configurações">
      <div className="card max-w-5xl mx-auto">
        
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

            <div className="flex justify-end mb-6">
              <button onClick={saveConfig} disabled={loading} className="btn-primary py-2 px-4 shadow-sm text-sm"><Save size={16} className="mr-2"/> Gravar Chaves Evolution API</button>
            </div>
            
            <div className="bg-slate-50 dark:bg-dark-surface border border-slate-200 dark:border-dark-border rounded-xl p-6 flex flex-col md:flex-row items-center gap-6 mt-4">
              <div className="flex-1">
                <div className="text-sm font-medium text-slate-500 mb-1">Status da Conexão</div>
                
                {waStatus === 'open' && <div className="text-xl font-bold text-green-600">Conectado e Pronto ✅</div>}
                {waStatus === 'connecting' && <div className="text-xl font-bold text-amber-500">Aguardando QR Code... ⏳</div>}
                {waStatus === 'closed' && <div className="text-xl font-bold text-slate-600 dark:text-slate-400">Desconectado ❌</div>}
                {waStatus === 'desconhecido' && <div className="text-xl font-bold text-slate-400">Clique para verificar</div>}
                {waStatus === 'erro_conexao' && <div className="text-xl font-bold text-red-500">Erro na Evolution API</div>}
              </div>
              
              <div className="flex flex-col gap-2 w-full md:w-auto">
                <button onClick={checkWaStatus} disabled={waCheckingStatus || waGeneratingQr || waDisconnecting} className="btn-secondary whitespace-nowrap w-full justify-center">
                  {waCheckingStatus ? <Loader2 className="animate-spin mr-2" size={18}/> : <RefreshCw size={18} className="mr-2"/>} 
                  Checar Status
                </button>
                
                {(waStatus === 'open' || waStatus === 'connecting' || waStatus === 'erro_conexao' || waStatus === 'desconhecido') && (
                  <button onClick={disconnectWa} disabled={waCheckingStatus || waGeneratingQr || waDisconnecting} className="btn-secondary text-red-600 hover:bg-red-50 border-red-200 mt-2 w-full justify-center">
                    {waDisconnecting ? <Loader2 className="animate-spin mr-2" size={18}/> : <PowerOff size={18} className="mr-2"/>}
                    Desconectar (Resetar Sessão)
                  </button>
                )}

                {(waStatus === 'closed' || waStatus === 'desconhecido' || waStatus === 'erro_conexao') && (
                  <button onClick={connectWa} disabled={waCheckingStatus || waGeneratingQr || waDisconnecting} className="btn-primary whitespace-nowrap mt-2 w-full justify-center">
                    {waGeneratingQr ? <Loader2 className="animate-spin mr-2" size={18}/> : <QrCode size={18} className="mr-2"/>}
                    Gerar QR Code
                  </button>
                )}
              </div>
            </div>

            {waQrCode && waStatus !== 'open' && (
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

             <div className="bg-slate-50 dark:bg-dark-surface p-6 rounded-xl border border-slate-200 dark:border-dark-border">
                <div className="flex items-center justify-between mb-6">
                  <h4 className="font-bold text-slate-800 dark:text-white">Robô de Automação Diária</h4>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input type="checkbox" className="sr-only peer" checked={scheduler.ativo} onChange={e => setScheduler({...scheduler, ativo: e.target.checked})} />
                    <div className="w-11 h-6 bg-slate-200 peer-focus:outline-none rounded-full peer dark:bg-slate-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all dark:border-slate-600 peer-checked:bg-primary-600"></div>
                  </label>
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
          </div>
        )}

      </div>
    </Layout>
  );
};
