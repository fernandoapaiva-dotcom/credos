import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '../components/ui/Layout';
import { Wallet, Users, FileWarning, TrendingUp } from 'lucide-react';

export const Dashboard: React.FC = () => {
  const navigate = useNavigate();
  return (
    <Layout title="Dashboard Geral">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        
        <div className="card flex items-center p-6 gap-4 border-l-4 border-l-primary-500">
          <div className="w-12 h-12 rounded-full bg-primary-100 text-primary-600 dark:bg-primary-900/40 dark:text-primary-400 flex items-center justify-center">
            <Wallet size={24} />
          </div>
          <div>
            <p className="text-sm text-slate-500 dark:text-slate-400 font-medium">Títulos em Aberto</p>
            <h3 className="text-2xl font-bold text-slate-900 dark:text-white">R$ 45.230,00</h3>
          </div>
        </div>
        
        <div className="card flex items-center p-6 gap-4 border-l-4 border-l-green-500">
          <div className="w-12 h-12 rounded-full bg-green-100 text-green-600 dark:bg-green-900/40 dark:text-green-400 flex items-center justify-center">
            <TrendingUp size={24} />
          </div>
          <div>
            <p className="text-sm text-slate-500 dark:text-slate-400 font-medium">Acordos Recebidos</p>
            <h3 className="text-2xl font-bold text-slate-900 dark:text-white">R$ 12.450,00</h3>
          </div>
        </div>
        
        <div className="card flex items-center p-6 gap-4 border-l-4 border-l-amber-500">
          <div className="w-12 h-12 rounded-full bg-amber-100 text-amber-600 dark:bg-amber-900/40 dark:text-amber-400 flex items-center justify-center">
            <Users size={24} />
          </div>
          <div>
            <p className="text-sm text-slate-500 dark:text-slate-400 font-medium">Clientes Ativos</p>
            <h3 className="text-2xl font-bold text-slate-900 dark:text-white">124</h3>
          </div>
        </div>
        
        <div className="card flex items-center p-6 gap-4 border-l-4 border-l-red-500">
          <div className="w-12 h-12 rounded-full bg-red-100 text-red-600 dark:bg-red-900/40 dark:text-red-400 flex items-center justify-center">
            <FileWarning size={24} />
          </div>
          <div>
            <p className="text-sm text-slate-500 dark:text-slate-400 font-medium">Em Cartório</p>
            <h3 className="text-2xl font-bold text-slate-900 dark:text-white">12</h3>
          </div>
        </div>

      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card">
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

        <div className="card">
          <h2 className="text-lg font-bold text-slate-800 dark:text-white mb-4">Resumo de Atividades</h2>
          <div className="flex items-center justify-center h-48 text-slate-400 text-sm">
            Gráfico de acompanhamento (A implementar)
          </div>
        </div>
      </div>
    </Layout>
  );
};
