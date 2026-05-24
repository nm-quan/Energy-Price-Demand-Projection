import React, { createContext, useContext, useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useLocation, useParams, Link } from 'react-router-dom';
import { Zap, Users, LogOut, ChevronRight } from 'lucide-react';
import { isAuthenticated, removeToken, getToken } from './lib/auth';
import { getMe } from './lib/api';

import Login from './pages/Login';
import ClientList from './pages/ClientList';
import ClientSetup from './pages/ClientSetup';
import BaselineAnalysis from './pages/BaselineAnalysis';
import ScenarioBuilder from './pages/ScenarioBuilder';
import Report from './pages/Report';

// Auth context
const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

function AuthProvider({ children }) {
  const [broker, setBroker] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (isAuthenticated()) {
      getMe()
        .then((res) => setBroker(res.data))
        .catch(() => {
          removeToken();
        })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  const logout = () => {
    removeToken();
    setBroker(null);
  };

  return (
    <AuthContext.Provider value={{ broker, setBroker, logout, loading }}>
      {children}
    </AuthContext.Provider>
  );
}

function RequireAuth({ children }) {
  const { loading } = useAuth();
  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
      </div>
    );
  }
  if (!isAuthenticated()) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

function Sidebar({ clientId, clientName }) {
  const { broker, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const isActive = (path) => location.pathname === path || location.pathname.startsWith(path + '/');

  return (
    <aside className="w-64 bg-slate-900 text-white flex flex-col min-h-screen flex-shrink-0">
      {/* Logo */}
      <div className="px-6 py-5 border-b border-slate-700 flex items-center gap-2">
        <div className="bg-indigo-600 rounded-lg p-1.5">
          <Zap size={18} className="text-white" />
        </div>
        <span className="font-semibold text-lg tracking-tight">EnergyScope</span>
      </div>

      {/* Broker info */}
      {broker && (
        <div className="px-6 py-4 border-b border-slate-700">
          <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Signed in as</p>
          <p className="text-sm font-medium text-white truncate">{broker.name}</p>
          {broker.firm && (
            <p className="text-xs text-slate-400 truncate">{broker.firm}</p>
          )}
        </div>
      )}

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        <Link
          to="/clients"
          className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
            isActive('/clients') && !clientId
              ? 'bg-indigo-600 text-white'
              : 'text-slate-300 hover:bg-slate-800 hover:text-white'
          }`}
        >
          <Users size={16} />
          Clients
        </Link>

        {clientId && (
          <div className="mt-2">
            <p className="px-3 py-1 text-xs text-slate-500 uppercase tracking-wider truncate">
              {clientName || 'Current Client'}
            </p>
            <Link
              to={`/clients/${clientId}/baseline`}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                isActive(`/clients/${clientId}/baseline`)
                  ? 'bg-slate-700 text-white'
                  : 'text-slate-400 hover:bg-slate-800 hover:text-white'
              }`}
            >
              <ChevronRight size={14} />
              Baseline Analysis
            </Link>
            <Link
              to={`/clients/${clientId}/scenarios`}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                isActive(`/clients/${clientId}/scenarios`)
                  ? 'bg-slate-700 text-white'
                  : 'text-slate-400 hover:bg-slate-800 hover:text-white'
              }`}
            >
              <ChevronRight size={14} />
              Scenarios
            </Link>
            <Link
              to={`/clients/${clientId}/report`}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                isActive(`/clients/${clientId}/report`)
                  ? 'bg-slate-700 text-white'
                  : 'text-slate-400 hover:bg-slate-800 hover:text-white'
              }`}
            >
              <ChevronRight size={14} />
              Report
            </Link>
          </div>
        )}
      </nav>

      {/* Logout */}
      <div className="px-3 py-4 border-t border-slate-700">
        <button
          onClick={handleLogout}
          className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-slate-400 hover:bg-slate-800 hover:text-white transition-colors w-full"
        >
          <LogOut size={16} />
          Sign out
        </button>
      </div>
    </aside>
  );
}

function AppLayout({ children }) {
  const params = useParams();
  const location = useLocation();

  // Extract clientId from URL if present
  const clientId = params.id || null;
  const [clientName, setClientName] = useState('');

  useEffect(() => {
    if (clientId) {
      // Try to get client name from session storage cache
      const cached = sessionStorage.getItem(`client_name_${clientId}`);
      if (cached) setClientName(cached);
    }
  }, [clientId]);

  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar clientId={clientId} clientName={clientName} />
      <main className="flex-1 overflow-auto">
        {children}
      </main>
    </div>
  );
}

function LayoutRoute({ children }) {
  return (
    <RequireAuth>
      <AppLayoutWrapper>{children}</AppLayoutWrapper>
    </RequireAuth>
  );
}

function AppLayoutWrapper({ children }) {
  const params = useParams();
  const [clientName, setClientName] = useState('');
  const clientId = params.id || null;

  useEffect(() => {
    if (clientId) {
      const cached = sessionStorage.getItem(`client_name_${clientId}`);
      if (cached) setClientName(cached);
    }
  }, [clientId]);

  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar clientId={clientId} clientName={clientName} />
      <main className="flex-1 overflow-auto">
        {children}
      </main>
    </div>
  );
}

function RootRedirect() {
  if (isAuthenticated()) {
    return <Navigate to="/clients" replace />;
  }
  return <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<RootRedirect />} />
          <Route
            path="/clients"
            element={
              <RequireAuth>
                <AppLayoutWrapper>
                  <ClientList />
                </AppLayoutWrapper>
              </RequireAuth>
            }
          />
          <Route
            path="/clients/new"
            element={
              <RequireAuth>
                <AppLayoutWrapper>
                  <ClientSetup />
                </AppLayoutWrapper>
              </RequireAuth>
            }
          />
          <Route
            path="/clients/:id/baseline"
            element={
              <RequireAuth>
                <AppLayoutWrapper>
                  <BaselineAnalysis />
                </AppLayoutWrapper>
              </RequireAuth>
            }
          />
          <Route
            path="/clients/:id/scenarios"
            element={
              <RequireAuth>
                <AppLayoutWrapper>
                  <ScenarioBuilder />
                </AppLayoutWrapper>
              </RequireAuth>
            }
          />
          <Route
            path="/clients/:id/report"
            element={
              <RequireAuth>
                <AppLayoutWrapper>
                  <Report />
                </AppLayoutWrapper>
              </RequireAuth>
            }
          />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
