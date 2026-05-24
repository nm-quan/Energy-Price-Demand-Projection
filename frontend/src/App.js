import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation, useParams, Link } from 'react-router-dom';
import { Zap, Users, ChevronRight } from 'lucide-react';

import ClientList from './pages/ClientList';
import ClientSetup from './pages/ClientSetup';
import BaselineAnalysis from './pages/BaselineAnalysis';
import ScenarioBuilder from './pages/ScenarioBuilder';
import Report from './pages/Report';

function Sidebar({ clientId, clientName }) {
  const location = useLocation();

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
    </aside>
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

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/clients" replace />} />
        <Route
          path="/clients"
          element={
            <AppLayoutWrapper>
              <ClientList />
            </AppLayoutWrapper>
          }
        />
        <Route
          path="/clients/new"
          element={
            <AppLayoutWrapper>
              <ClientSetup />
            </AppLayoutWrapper>
          }
        />
        <Route
          path="/clients/:id/baseline"
          element={
            <AppLayoutWrapper>
              <BaselineAnalysis />
            </AppLayoutWrapper>
          }
        />
        <Route
          path="/clients/:id/scenarios"
          element={
            <AppLayoutWrapper>
              <ScenarioBuilder />
            </AppLayoutWrapper>
          }
        />
        <Route
          path="/clients/:id/report"
          element={
            <AppLayoutWrapper>
              <Report />
            </AppLayoutWrapper>
          }
        />
      </Routes>
    </BrowserRouter>
  );
}
