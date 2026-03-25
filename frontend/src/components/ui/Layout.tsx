import React from 'react';
import { useAuth } from '../../context/AuthContext';
import { useTheme } from '../../context/ThemeContext';
import { useNavigate, useLocation } from 'react-router-dom';
import { LayoutDashboard, Users, FileText, UploadCloud, LogOut, Sun, Moon, ArrowLeftRight, Settings, Shield } from 'lucide-react';
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

  const handleSwitchCompany = () => {
    setCompany('');
    navigate('/companies');
  };

  const menu = [
    { label: 'Dashboard', icon: LayoutDashboard, path: '/dashboard' },
    { label: 'CRM & Títulos', icon: Users, path: '/crm' },
    { label: 'Importar PDF', icon: UploadCloud, path: '/import' },
    { label: 'Relatórios', icon: FileText, path: '/reports' },
    { label: 'Configurações', icon: Settings, path: '/settings' },
    ...(user?.perfil === 'admin' ? [{ label: 'Usuários', icon: Shield, path: '/users' }] : []),
  ];

  return (
    <div className="flex h-screen bg-slate-50 dark:bg-dark-bg transition-colors">
      
      {/* SIDEBAR */}
      <aside className="w-64 bg-white dark:bg-dark-surface border-r border-slate-200 dark:border-dark-border flex flex-col transition-colors z-20 shadow-sm relative">
        <div className="h-16 flex items-center px-6 border-b border-slate-100 dark:border-dark-border/50 font-bold text-xl text-primary-600 dark:text-primary-400 gap-3">
          <img src={companyLogo || "/logo.png"} className="w-10 h-10 object-contain rounded" alt="Credos" />
          <span className="truncate">{title === 'Dashboard Geral' ? 'Credos' : title}</span>
        </div>
        
        <nav className="flex-1 py-6 px-4 space-y-1">
          {menu.map((item) => {
            const isActive = location.pathname.startsWith(item.path);
            const Icon = item.icon;
            return (
              <button
                key={item.path}
                onClick={() => navigate(item.path)}
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

        <div className="p-4 border-t border-slate-200 dark:border-dark-border">
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
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <header className="h-16 bg-white/80 dark:bg-dark-surface/80 backdrop-blur-md border-b border-slate-200 dark:border-dark-border flex items-center px-8 z-10">
          <h1 className="text-xl font-bold text-slate-800 dark:text-white">{title}</h1>
        </header>
        <div className="flex-1 overflow-auto p-8 relative">
          <div className="max-w-7xl mx-auto h-full animate-fade-in">
            {children}
          </div>
        </div>
      </main>

    </div>
  );
};

