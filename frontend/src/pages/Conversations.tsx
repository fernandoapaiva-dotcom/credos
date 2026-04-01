import React, { useEffect, useState, useMemo } from 'react';
import { Layout } from '../components/ui/Layout';
import { api } from '../context/AuthContext';
import { Loader2, Search, MessageCircle, FileText, Printer, Calendar, Clock, AlertCircle } from 'lucide-react';

interface ChatMessage {
  role: 'user' | 'model';
  text: string;
}

interface Conversation {
  id: number;
  numero_whatsapp: string;
  cliente_nome: string;
  estado: string;
  ultima_interacao: string;
  history: ChatMessage[];
}

export const Conversations: React.FC = () => {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedChat, setSelectedChat] = useState<Conversation | null>(null);
  
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');

  useEffect(() => {
    fetchConversations();
  }, []);

  const fetchConversations = async () => {
    setLoading(true);
    try {
      const res = await api.get('/crm/conversations');
      setConversations(res.data.conversations || []);
    } catch (e) {
      console.error("Erro ao buscar histórico do WhatsApp", e);
    } finally {
      setLoading(false);
    }
  };

  const filteredConversations = useMemo(() => {
    return conversations.filter(c => 
      (c.cliente_nome?.toLowerCase() || '').includes(searchTerm.toLowerCase()) || 
      (c.numero_whatsapp || '').includes(searchTerm.toLowerCase())
    );
  }, [conversations, searchTerm]);

  const filteredHistory = useMemo(() => {
    if (!selectedChat?.history) return [];
    return selectedChat.history.filter(msg => {
      // @ts-ignore - Aceitando compatibilidade retroativa para mensagens antigas sem timestamp
      if (!msg.timestamp) return true; 
      // @ts-ignore
      const msgDateStr = msg.timestamp.split(' ')[0]; // "YYYY-MM-DD"
      
      if (startDate && msgDateStr < startDate) return false;
      if (endDate && msgDateStr > endDate) return false;
      
      return true;
    });
  }, [selectedChat, startDate, endDate]);

  const handlePrint = () => {
    window.print();
  };

  return (
    <Layout title="Histórico do WhatsApp">
      <div className="flex flex-col lg:flex-row gap-6 h-[calc(100vh-8rem)] print:h-auto print:block">
        
        {/* LADO ESQUERDO: LISTA DE CONVERSAS (Oculto na Impressão) */}
        <div className="card w-full lg:w-1/3 flex flex-col p-0 overflow-hidden shadow-lg print:hidden">
          <div className="p-4 border-b border-slate-200 dark:border-dark-border bg-slate-50 dark:bg-dark-bg/50">
            <h3 className="font-bold text-lg dark:text-white flex items-center gap-2 mb-3">
              <MessageCircle size={20} className="text-primary-500" />
              Sessões do WhatsApp
              {loading && <Loader2 className="animate-spin text-primary-500 ml-auto" size={16} />}
            </h3>
            <div className="relative">
              <Search className="absolute left-3 top-3 text-slate-400" size={18} />
              <input 
                type="text" 
                placeholder="Buscar por cliente ou número..." 
                className="input-field pl-10 py-2.5 bg-white dark:bg-dark-surface"
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
              />
            </div>
          </div>
          
          <div className="flex-1 overflow-y-auto p-2 custom-scrollbar">
            {filteredConversations.length === 0 && !loading ? (
              <div className="text-center py-10 text-slate-400">
                <AlertCircle className="mx-auto mb-2 opacity-20" size={32} />
                <p className="text-sm">Nenhum histórico encontrado para os filtros.</p>
              </div>
            ) : (
              filteredConversations.map(conv => (
                <div 
                  key={conv.id} 
                  onClick={() => setSelectedChat(conv)}
                  className={`p-3 rounded-xl mb-2 cursor-pointer transition-all border ${
                    selectedChat?.id === conv.id 
                      ? 'bg-primary-50 border-primary-300 dark:bg-primary-900/30 dark:border-primary-700' 
                      : 'bg-white border-transparent hover:border-slate-200 hover:bg-slate-50 dark:bg-dark-surface dark:hover:bg-dark-bg/50'
                  }`}
                >
                  <div className="flex justify-between items-start mb-1">
                    <p className="font-bold text-sm text-slate-900 dark:text-white truncate pr-2 max-w-[70%]">{conv.cliente_nome}</p>
                    <span className="text-[10px] text-slate-400 font-bold uppercase whitespace-nowrap">
                      {conv.ultima_interacao ? conv.ultima_interacao.split(' ')[0] : 'S/ Data'}
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <p className="text-xs text-slate-500 dark:text-slate-400 truncate max-w-[75%] font-mono">
                      {conv.numero_whatsapp}
                    </p>
                    {selectedChat?.id === conv.id && <span className="w-2 h-2 rounded-full bg-primary-500 animate-pulse"></span>}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* LADO DIREITO: CHAT / CONVERSA (Visível inteira na Impressão) */}
        <div className="card w-full lg:w-2/3 flex flex-col p-0 shadow-lg border-slate-200/60 dark:border-dark-border print:w-full print:shadow-none print:border-none print:h-auto overflow-hidden bg-[#e5ddd5] dark:bg-dark-bg/80 print:bg-white">
          {selectedChat ? (
            <>
              {/* HEADER DO CHAT */}
              <div className="px-6 py-4 bg-white dark:bg-dark-surface border-b border-slate-200 dark:border-dark-border flex flex-col xl:flex-row justify-between xl:items-center gap-4 z-10 print:border-b-2 print:border-black print:pb-2">
                <div>
                  <h2 className="text-xl font-black text-slate-900 dark:text-white flex items-center gap-2">
                    {selectedChat.cliente_nome}
                    <span className="px-2 py-0.5 bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400 text-[10px] rounded-full uppercase tracking-wider print:border print:border-black print:bg-transparent print:text-black">
                      Automação
                    </span>
                  </h2>
                  <p className="text-sm font-mono text-slate-500 flex items-center gap-1.5 mt-1 print:hidden">
                    <Calendar size={12} /> Última interação: {selectedChat.ultima_interacao || 'Sem data'}
                  </p>
                  <p className="text-xs text-slate-400 font-bold uppercase mt-0.5 print:text-black">
                    WhatsApp: {selectedChat.numero_whatsapp} | Status: {selectedChat.estado}
                    {startDate || endDate ? ` | Período: ${startDate || 'Início'} até ${endDate || 'Hoje'}` : ''}
                  </p>
                </div>
                
                <div className="flex flex-wrap items-center gap-3 print:hidden">
                  <div className="flex items-center gap-2 bg-slate-50 dark:bg-dark-bg p-2 rounded-xl border border-slate-200 dark:border-dark-border">
                    <div className="flex flex-col">
                      <span className="text-[9px] text-slate-500 font-bold uppercase mb-0.5 ml-1">De</span>
                      <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} className="text-xs p-1.5 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-dark-surface dark:text-white shadow-sm" />
                    </div>
                    <div className="flex flex-col">
                      <span className="text-[9px] text-slate-500 font-bold uppercase mb-0.5 ml-1">Até</span>
                      <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} className="text-xs p-1.5 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-dark-surface dark:text-white shadow-sm" />
                    </div>
                  </div>
                  
                  <button 
                    onClick={handlePrint}
                    className="p-3 bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-primary-100 hover:text-primary-600 rounded-xl transition-all shadow-sm font-bold ml-auto"
                    title="Exportar como PDF / Imprimir"
                  >
                    <Printer size={20} />
                  </button>
                </div>
              </div>

              {/* CORPO DO CHAT */}
              <div className="flex-1 overflow-y-auto p-4 lg:p-6 space-y-4 custom-scrollbar bg-transparent print:h-auto print:overflow-visible print:p-0 print:pt-4 print:block relative" style={{ backgroundImage: "url('https://transparenttextures.com/patterns/cubes.png')", opacity: 0.9 }}>
                {filteredHistory.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-full text-slate-500/80">
                    <div className="bg-amber-100 text-amber-800 p-4 rounded-xl shadow-sm text-sm text-center max-w-sm print:border print:border-black">
                      Nenhuma conversa textual direta registrada nesta sessão de negociação.
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="flex justify-center mb-6">
                      <span className="bg-[#d1e9f2] dark:bg-[#202c33] dark:text-[#8696a0] px-3 py-1 rounded-lg text-xs font-bold text-slate-600 shadow-sm print:border print:border-black">
                        Início do Histórico Salvo
                      </span>
                    </div>

                    {filteredHistory.map((msg, index) => {
                      const isUser = msg.role === 'user';
                      return (
                        <div key={index} className={`flex ${isUser ? 'justify-end' : 'justify-start'} print:break-inside-avoid print:mb-4`}>
                          <div className={`
                            relative max-w-[85%] lg:max-w-[70%] p-3 rounded-2xl shadow-sm
                            ${isUser 
                              ? 'bg-[#dcf8c6] dark:bg-[#005c4b] text-slate-900 dark:text-slate-200 rounded-tr-none' 
                              : 'bg-white dark:bg-[#202c33] text-slate-900 dark:text-slate-200 rounded-tl-none border border-slate-100 dark:border-transparent'
                            }
                            print:bg-white print:border print:border-slate-300 print:text-black print:rounded-lg print:shadow-none
                          `}>
                            {/* CAUDA DO BALÃO DE CHAT (OCULTA NO PRINT PARA FICAR LIMPO) */}
                            <div className={`absolute top-0 w-4 h-4 print:hidden ${isUser ? '-right-2 bg-[#dcf8c6] dark:bg-[#005c4b]' : '-left-2 bg-white dark:bg-[#202c33]'}`} style={{ clipPath: isUser ? "polygon(0 0, 0% 100%, 100% 0)" : "polygon(100% 0, 0 0, 100% 100%)"}}></div>

                            {!isUser && (
                              <p className="text-[10px] font-black uppercase text-primary-600 dark:text-primary-400 mb-1 tracking-wider print:text-black">
                                Analu (Inteligência Artificial)
                              </p>
                            )}
                            {isUser && (
                              <p className="text-[10px] font-black uppercase text-green-700 dark:text-green-400 mb-1 tracking-wider text-right print:text-black">
                                Cliente
                              </p>
                            )}
                            
                            <div className="text-sm whitespace-pre-wrap leading-relaxed font-medium">
                              {msg.text}
                            </div>
                            
                            <div className={`text-[9px] mt-2 opacity-60 font-bold uppercase tracking-widest ${isUser ? 'text-right text-green-800 dark:text-green-300' : 'text-left'} flex items-center gap-1 ${isUser ? 'justify-end' : 'justify-start'} print:text-black`}>
                              <Clock size={8} /> 
                              {/* @ts-ignore */}
                              {msg.timestamp ? msg.timestamp : 'Registro Legado'}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </>
                )}
              </div>
            </>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-slate-400 dark:text-slate-600 bg-slate-100/50 dark:bg-dark-bg/20 print:hidden">
              <div className="p-8 rounded-full bg-white dark:bg-dark-surface shadow-lg mb-4">
                <FileText size={48} className="opacity-20" />
              </div>
              <h4 className="text-lg font-black">Nenhuma Conversa Selecionada</h4>
              <p className="text-sm text-center max-w-xs mt-2 opacity-80">Selecione um cliente no painel ao lado para visualizar e exportar o histórico do WhatsApp.</p>
            </div>
          )}
        </div>

      </div>
    </Layout>
  );
};
