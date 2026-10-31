import React from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import { Login } from './pages/Login';
import { Companies } from './pages/Companies';
import { Dashboard } from './pages/Dashboard';
import { CRM } from './pages/CRM';
import { CartorioQueue } from './pages/CartorioQueue';
import { ImportPDF } from './pages/ImportPDF';
import { Reports } from './pages/Reports';
import { Settings } from './pages/Settings';
import { Users } from './pages/Users';
import { Conversations } from './pages/Conversations';

const PrivateRoute: React.FC<{ children: React.ReactNode, requireCompany?: boolean }> = ({ children, requireCompany }) => {
  const { user, companyCnpj } = useAuth();
  const location = useLocation();
  
  if (!user) {
    // Preservar o sso_token se ele existir na URL atual
    if (location.search) {
      console.log('DEBUG SSO Catch: Usuário não logado, preservando parâmetros para login:', location.search);
    }
    return <Navigate to={`/login${location.search}`} replace />;
  }
  
  if (requireCompany && !companyCnpj) {
    return <Navigate to="/companies" replace />;
  }
  
  return <>{children}</>;
};

const HomeRedirect: React.FC = () => {
  const location = useLocation();
  return <Navigate to={`/dashboard${location.search}`} replace />;
};

function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            
            <Route path="/companies" element={
              <PrivateRoute>
                <Companies />
              </PrivateRoute>
            } />
            
            <Route path="/dashboard" element={
              <PrivateRoute requireCompany>
                <Dashboard />
              </PrivateRoute>
            } />

            <Route path="/crm" element={
              <PrivateRoute requireCompany>
                <CRM />
              </PrivateRoute>
            } />

            <Route path="/cartorio" element={
              <PrivateRoute requireCompany>
                <CartorioQueue />
              </PrivateRoute>
            } />

            <Route path="/conversations" element={
              <PrivateRoute requireCompany>
                <Conversations />
              </PrivateRoute>
            } />

            <Route path="/import" element={
              <PrivateRoute requireCompany>
                <ImportPDF />
              </PrivateRoute>
            } />

            <Route path="/reports" element={
              <PrivateRoute requireCompany>
                <Reports />
              </PrivateRoute>
            } />

            <Route path="/settings" element={
              <PrivateRoute requireCompany>
                <Settings />
              </PrivateRoute>
            } />

            <Route path="/users" element={
              <PrivateRoute>
                <Users />
              </PrivateRoute>
            } />
            
            <Route path="/" element={<HomeRedirect />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ThemeProvider>
  );
}

export default App;
