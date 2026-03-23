import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '../components/ui/Layout';
import { api } from '../context/AuthContext';
import { Wallet, Users, FileWarning, TrendingUp, Loader2, RefreshCw, Send } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

interface DashboardData {
  stats: {
    total_aberto: number;
    total_recebido: number;
    total_clientes: number;
    total_cartorio: number;
    total_logs: number;
  };
  chart_data: Array<{
    name: string;
    recebido: number;
    pendente: number;
  }>;
}

export const Dashboard: React.FC = () => {
  const navigate = useNavigate();
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchStats();
  }, []);

  const fetchStats = async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const res = await api.get('/crm/dashboard-stats');
      setData(res.data);
    } catch (err) {
      console.error("Erro ao buscar stats", err);
    } finally {
      setLoading(false);
    }
  };

  const formatCurrency = (val: number) => {
    return val.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
  };

  if (loading) {
    return (
      <Layout title="Dashboard Geral">
        <div className="flex items-center justify-center h-64">
          <Loader2 className="animate-spin text-primary-500" size={48} />
        </div>
      </Layout>
    );
  }

  return (
    <Layout title="Dashboard Geral">
      <div className="flex justify-between items-center mb-6">
        <div>
           <h2 className="text-sm font-bold text-slate-400 uppercase tracking-widest">Resumo Financeiro</h2>
        </div>
        <button 
          onClick={() => fetchStats(false)} 
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-white dark:bg-dark-surface border border-slate-200 dark:border-dark-border text-slate-600 dark:text-slate-300 hover:text-primary-600 hover:border-primary-200 transition-all shadow-sm active:scale-95"
        >
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          <span className="text-sm font-bold">Atualizar</span>
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        
        <div className="card flex items-center p-6 gap-4 border-l-4 border-l-primary-500">
          <div className="w-12 h-12 rounded-full bg-primary-100 text-primary-600 dark:bg-primary-900/40 dark:text-primary-400 flex items-center justify-center">
            <Wallet size={24} />
          </div>
          <div>
            <p className="text-sm text-slate-500 dark:text-slate-400 font-medium">Títulos em Aberto</p>
            <h3 className="text-2xl font-bold text-slate-900 dark:text-white">{formatCurrency(data?.stats?.total_aberto || 0)}</h3>
          </div>
        </div>
        
        <div className="card flex items-center p-6 gap-4 border-l-4 border-l-green-500">
          <div className="w-12 h-12 rounded-full bg-green-100 text-green-600 dark:bg-green-900/40 dark:text-green-400 flex items-center justify-center">
            <TrendingUp size={24} />
          </div>
          <div>
            <p className="text-sm text-slate-500 dark:text-slate-400 font-medium">Acordos Recebidos</p>
            <h3 className="text-2xl font-bold text-slate-900 dark:text-white">{formatCurrency(data?.stats?.total_recebido || 0)}</h3>
          </div>
        </div>
        
        <div className="card flex items-center p-6 gap-4 border-l-4 border-l-amber-500">
          <div className="w-12 h-12 rounded-full bg-amber-100 text-amber-600 dark:bg-amber-900/40 dark:text-amber-400 flex items-center justify-center">
            <Users size={24} />
          </div>
          <div>
            <p className="text-sm text-slate-500 dark:text-slate-400 font-medium">Clientes Ativos</p>
            <h3 className="text-2xl font-bold text-slate-900 dark:text-white">{data?.stats?.total_clientes || 0}</h3>
          </div>
        </div>
        
        <div className="card flex items-center p-6 gap-4 border-l-4 border-l-red-500">
          <div className="w-12 h-12 rounded-full bg-red-100 text-red-600 dark:bg-red-900/40 dark:text-red-400 flex items-center justify-center">
            <FileWarning size={24} />
          </div>
          <div>
            <p className="text-sm text-slate-500 dark:text-slate-400 font-medium">Em Cartório</p>
            <h3 className="text-2xl font-bold text-slate-900 dark:text-white">{data?.stats?.total_cartorio || 0}</h3>
          </div>
        </div>

      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card min-h-[400px]">
          <h2 className="text-lg font-bold text-slate-800 dark:text-white mb-6">Resumo de Atividades</h2>
          <div className="h-[300px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data?.chart_data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorRecebido" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.1}/>
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                  </linearGradient>
                  <linearGradient id="colorPendente" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#6366f1" stopOpacity={0.1}/>
                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E2E8F0" />
                <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{fill: '#94a3b8', fontSize: 12}} />
                <YAxis hide />
                <Tooltip 
                  contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 15px -3px rgba(0,0,0,0.1)' }}
                  formatter={(value: any) => [formatCurrency(Number(value || 0)), '']}
                />
                <Area type="monotone" dataKey="recebido" stroke="#10b981" strokeWidth={3} fillOpacity={1} fill="url(#colorRecebido)" name="Recebido" />
                <Area type="monotone" dataKey="pendente" stroke="#6366f1" strokeWidth={3} fillOpacity={1} fill="url(#colorPendente)" name="Pendente" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <div className="flex gap-4 mt-4 justify-center">
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-green-500"></span>
              <span className="text-xs text-slate-500 dark:text-slate-400 font-medium">Recebido</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-primary-500"></span>
              <span className="text-xs text-slate-500 dark:text-slate-400 font-medium">Pendente</span>
            </div>
          </div>
        </div>

        <div className="card">
          <h2 className="text-lg font-bold text-slate-800 dark:text-white mb-4">Métricas de Performance</h2>
          <div className="grid grid-cols-1 gap-4 mb-6">
             <div className="p-4 rounded-2xl bg-slate-50 dark:bg-dark-bg/50 border border-slate-100 dark:border-dark-border flex items-center justify-between">
                <div className="flex items-center gap-3">
                   <div className="p-2 rounded-lg bg-primary-100 dark:bg-primary-900/30 text-primary-600 dark:text-primary-400">
                     <Send size={18} />
                   </div>
                   <span className="text-sm font-bold text-slate-600 dark:text-slate-400">Total Mensagens Enviadas</span>
                </div>
                <span className="text-xl font-black text-slate-900 dark:text-white">{data?.stats?.total_logs || 0}</span>
             </div>
          </div>

          <h2 className="text-lg font-bold text-slate-800 dark:text-white mb-4">Ações Rápidas</h2>
          <div className="space-y-3">
             <button onClick={() => navigate('/import')} className="w-full text-left px-4 py-3 rounded-lg border border-slate-200 dark:border-dark-border hover:bg-slate-50 dark:hover:bg-dark-bg transition-colors flex items-center justify-between group">
               <span className="font-medium text-slate-700 dark:text-slate-300">Importar novo lote de PDF</span>
               <span className="text-primary-500 opacity-0 group-hover:opacity-100 transition-opacity">→</span>
             </button>
             <button onClick={() => navigate('/crm')} className="w-full text-left px-4 py-3 rounded-lg border border-slate-200 dark:border-dark-border hover:bg-slate-50 dark:hover:bg-dark-bg transition-colors flex items-center justify-between group">
               <span className="font-medium text-slate-700 dark:text-slate-300">Revisar títulos e carteira</span>
               <span className="text-primary-500 opacity-0 group-hover:opacity-100 transition-opacity">→</span>
             </button>
             <button onClick={() => navigate('/reports')} className="w-full text-left px-4 py-3 rounded-lg border border-slate-200 dark:border-dark-border hover:bg-slate-50 dark:hover:bg-dark-bg transition-colors flex items-center justify-between group">
               <span className="font-medium text-slate-700 dark:text-slate-300">Gerar relatório de auditoria</span>
               <span className="text-primary-500 opacity-0 group-hover:opacity-100 transition-opacity">→</span>
             </button>
          </div>
        </div>
      </div>
    </Layout>
  );
};

