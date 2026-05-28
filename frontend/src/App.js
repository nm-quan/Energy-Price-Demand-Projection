import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation, useParams, Link } from 'react-router-dom';

import ClientList from './pages/ClientList';
import ClientSetup from './pages/ClientSetup';
import StorePortfolio from './pages/StorePortfolio';
import BaselineAnalysis from './pages/BaselineAnalysis';
import ScenarioBuilder from './pages/ScenarioBuilder';
import Report from './pages/Report';
import AIAnalysis from './pages/AIAnalysis';

function Sidebar({ clientId, clientName }) {
  const location = useLocation();
  const isActive = (path) => location.pathname === path || location.pathname.startsWith(path + '/');

  const NavItem = ({ to, label, active, testId }) => (
    <Link
      to={to}
      data-testid={testId}
      className={`block px-3 py-2 rounded-lg text-sm transition-all ${
        active
          ? 'bg-lime text-forest-900 font-semibold'
          : 'text-forest-100/80 hover:bg-forest-700/40 hover:text-white'
      }`}
    >
      {label}
    </Link>
  );

  return (
    <aside
      className="w-60 bg-forest-800 text-white flex flex-col min-h-screen flex-shrink-0 border-r border-forest-900"
      data-testid="app-sidebar"
    >
      <div className="px-6 pt-6 pb-5 border-b border-forest-700/50">
        <Link to="/clients" className="font-display text-2xl font-semibold tracking-tightest">
          EnergyScope
        </Link>
      </div>

      <nav className="flex-1 px-3 py-5 space-y-1">
        <NavItem
          to="/clients"
          label="Clients"
          active={isActive('/clients') && !clientId}
          testId="sidebar-nav-clients"
        />

        {clientId && (
          <div className="mt-5">
            <p className="px-3 py-1 text-[10px] text-lime/90 uppercase tracking-[0.2em] font-medium truncate">
              {clientName || 'Current Client'}
            </p>
            <div className="mt-1 space-y-1">
              <NavItem
                to={`/clients/${clientId}/portfolio`}
                label="Portfolio"
                active={isActive(`/clients/${clientId}/portfolio`)}
                testId="sidebar-nav-portfolio"
              />
              <NavItem
                to={`/clients/${clientId}/baseline`}
                label="Baseline"
                active={isActive(`/clients/${clientId}/baseline`)}
                testId="sidebar-nav-baseline"
              />
              <NavItem
                to={`/clients/${clientId}/scenarios`}
                label="Scenarios"
                active={isActive(`/clients/${clientId}/scenarios`)}
                testId="sidebar-nav-scenarios"
              />
              <NavItem
                to={`/clients/${clientId}/ai`}
                label="Chat"
                active={isActive(`/clients/${clientId}/ai`)}
                testId="sidebar-nav-ai"
              />
              <NavItem
                to={`/clients/${clientId}/report`}
                label="Reports"
                active={isActive(`/clients/${clientId}/report`)}
                testId="sidebar-nav-report"
              />
            </div>
          </div>
        )}
      </nav>

      <div className="px-6 py-4 border-t border-forest-700/50 text-[10px] text-forest-100/40 tracking-widest uppercase">
        v2.0
      </div>
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
    <div className="flex min-h-screen bg-cream grain">
      <Sidebar clientId={clientId} clientName={clientName} />
      <main className="flex-1 overflow-auto relative z-10">{children}</main>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/clients" replace />} />
        <Route path="/clients" element={<AppLayoutWrapper><ClientList /></AppLayoutWrapper>} />
        <Route path="/clients/new" element={<AppLayoutWrapper><ClientSetup /></AppLayoutWrapper>} />
        <Route path="/clients/:id/portfolio" element={<AppLayoutWrapper><StorePortfolio /></AppLayoutWrapper>} />
        <Route path="/clients/:id/baseline" element={<AppLayoutWrapper><BaselineAnalysis /></AppLayoutWrapper>} />
        <Route path="/clients/:id/scenarios" element={<AppLayoutWrapper><ScenarioBuilder /></AppLayoutWrapper>} />
        <Route path="/clients/:id/ai" element={<AppLayoutWrapper><AIAnalysis /></AppLayoutWrapper>} />
        <Route path="/clients/:id/report" element={<AppLayoutWrapper><Report /></AppLayoutWrapper>} />
      </Routes>
    </BrowserRouter>
  );
}
