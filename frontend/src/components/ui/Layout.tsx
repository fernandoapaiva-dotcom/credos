import React, { useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { useTheme } from '../../context/ThemeContext';
import { useNavigate, useLocation } from 'react-router-dom';
import { LayoutDashboard, Users, FileText, UploadCloud, LogOut, Sun, Moon, ArrowLeftRight, Settings, Shield, Menu, X, MessageSquare } from 'lucide-react';
import clsx from 'clsx';

interface LayoutProps {
  children: React.ReactNode;
  title: string;
}

export const Layout: React.FC<LayoutProps> = ({ children, title }) => {
  const { user, logout, setCompany, companyLogo } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const navigate = useNavigate();
  const location = useLocation();
  const [isSidebarOpen, setSidebarOpen] = useState(false);

  const handleSwitchCompany = () => {
    setCompany('');
    navigate('/companies');
  };

  const menu = [
    { label: 'Dashboard', icon: LayoutDashboard, path: '/dashboard' },
    { label: 'CRM & Títulos', icon: Users, path: '/crm' },
    { label: 'Histórico WhatsApp', icon: MessageSquare, path: '/conversations' },
    { label: 'Importar PDF', icon: UploadCloud, path: '/import' },
    { label: 'Relatórios', icon: FileText, path: '/reports' },
    { label: 'Configurações', icon: Settings, path: '/settings' },
    ...(user?.perfil === 'admin' ? [{ label: 'Usuários', icon: Shield, path: '/users' }] : []),
  ];

  const handleNavigate = (path: string) => {
    navigate(path);
    setSidebarOpen(false); // Fecha a sidebar ao navegar no mobile
  };

  return (
    <div className="flex h-screen bg-slate-50 dark:bg-dark-bg transition-colors overflow-hidden print:h-auto print:overflow-visible print:block">
      
      {/* MOBILE OVERLAY */}
      {isSidebarOpen && (
        <div 
          className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-30 lg:hidden animate-fade-in"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* SIDEBAR */}
      <aside className={clsx(
        "fixed inset-y-0 left-0 w-64 bg-white dark:bg-dark-surface border-r border-slate-200 dark:border-dark-border flex flex-col transition-all duration-300 z-40 transform lg:translate-x-0 lg:static lg:inset-0 shadow-xl lg:shadow-none print:hidden",
        isSidebarOpen ? "translate-x-0" : "-translate-x-full"
      )}>
        <div className="h-16 flex items-center px-6 border-b border-slate-100 dark:border-dark-border/50 font-bold text-xl text-primary-600 dark:text-primary-400 gap-3">
          <div className="w-10 h-10 bg-white rounded flex items-center justify-center p-1 shadow-sm">
            <img src={companyLogo || "/logo.png"} className="max-w-full max-h-full object-contain" alt="Logo" />
          </div>
          <span className="truncate">{title === 'Dashboard Geral' ? 'Credos' : title}</span>
          <button 
            className="lg:hidden ml-auto p-2 text-slate-400 hover:text-slate-600 transition-colors"
            onClick={() => setSidebarOpen(false)}
          >
            <X size={20} />
          </button>
        </div>
        
        <nav className="flex-1 py-6 px-4 space-y-1 overflow-y-auto custom-scrollbar">
          {menu.map((item) => {
            const isActive = location.pathname.startsWith(item.path);
            const Icon = item.icon;
            return (
              <button
                key={item.path}
                onClick={() => handleNavigate(item.path)}
                className={clsx(
                  "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all group",
                  isActive 
                    ? "bg-primary-50 text-primary-700 dark:bg-primary-900/20 dark:text-primary-400" 
                    : "text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-dark-bg/50 dark:hover:text-slate-200"
                )}
              >
                <Icon size={18} className={isActive ? "text-primary-600 dark:text-primary-400" : "text-slate-400 group-hover:text-slate-500"} />
                {item.label}
              </button>
            )
          })}
        </nav>

        <div className="p-4 border-t border-slate-200 dark:border-dark-border bg-white dark:bg-dark-surface">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-full bg-slate-200 dark:bg-slate-800 flex items-center justify-center text-slate-700 dark:text-slate-300 font-bold text-sm">
              {user?.nome_completo?.[0] || 'U'}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-slate-900 dark:text-white truncate">{user?.nome_completo}</p>
              <p className="text-xs text-slate-500 dark:text-slate-400 truncate text-ellipsis">{user?.username}</p>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <button onClick={handleSwitchCompany} className="flex justify-center items-center py-2 rounded-lg text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors" title="Trocar Empresa">
              <ArrowLeftRight size={16} />
            </button>
            <button onClick={toggleTheme} className="flex justify-center items-center py-2 rounded-lg text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors" title="Alternar Tema">
              {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
            </button>
            <button onClick={() => {logout(); navigate('/login');}} className="flex justify-center items-center py-2 rounded-lg text-red-500 hover:bg-red-50 dark:hover:bg-red-900/10 transition-colors" title="Sair">
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>

      {/* MAIN CONTENT */}
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden relative print:overflow-visible print:block">
        <header className="h-16 bg-white/80 dark:bg-dark-surface/80 backdrop-blur-md border-b border-slate-200 dark:border-dark-border flex items-center px-4 lg:px-8 z-10 gap-4 print:hidden">
          <button 
            className="lg:hidden p-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-dark-bg/50 rounded-lg transition-colors"
            onClick={() => setSidebarOpen(true)}
          >
            <Menu size={24} />
          </button>
          <h1 className="text-lg lg:text-xl font-bold text-slate-800 dark:text-white truncate">{title}</h1>
        </header>
        <div className="flex-1 overflow-auto p-4 lg:p-8 relative print:p-0 print:overflow-visible print:block">
          <div className="max-w-7xl mx-auto h-full animate-fade-in print:max-w-none print:w-full print:block">
            {children}
          </div>
        </div>
      </main>

    </div>
  );
};

