import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Plus, MapPin, Zap, CheckCircle, XCircle, AlertCircle, Sparkles } from 'lucide-react';
import { getClients, fmtCurrency, fmtNumber } from '../lib/api';

const DEMO_CLIENT_ID = 'client-demo-001';

function StatusBadge({ status }) {
  const styles = {
    draft: 'bg-slate-100 text-slate-600',
    active: 'bg-forest-100 text-forest-800',
    quoted: 'bg-lime-100 text-forest-900',
  };
  const cls = styles[status?.toLowerCase()] || styles.draft;
  const label = status
    ? status.charAt(0).toUpperCase() + status.slice(1).toLowerCase()
    : 'Draft';
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${cls}`}>
      {label}
    </span>
  );
}

function DemoBadge() {
  return (
    <span
      data-testid="demo-badge"
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold bg-lime-400 text-forest-900"
    >
      <Sparkles size={11} />
      DEMO
    </span>
  );
}

function DataChip({ present, label }) {
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs ${
        present ? 'bg-forest-100 text-forest-800' : 'bg-slate-100 text-slate-500'
      }`}
    >
      {present ? <CheckCircle size={11} /> : <XCircle size={11} />}
      {label}
    </span>
  );
}

function SkeletonCard() {
  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-5 animate-pulse">
      <div className="h-5 bg-slate-200 rounded w-2/3 mb-3" />
      <div className="h-3 bg-slate-100 rounded w-full mb-2" />
      <div className="h-3 bg-slate-100 rounded w-1/2 mb-4" />
      <div className="flex gap-2">
        <div className="h-5 bg-slate-100 rounded-full w-20" />
        <div className="h-5 bg-slate-100 rounded-full w-20" />
      </div>
    </div>
  );
}

export default function ClientList() {
  const navigate = useNavigate();
  const [clients, setClients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    getClients()
      .then((res) => setClients(res.data))
      .catch(() => setError('Failed to load clients. Please try again.'))
      .finally(() => setLoading(false));
  }, []);

  const handleCardClick = (client) => {
    // Demo client goes straight to its baseline (it's fully set up)
    if (client.id === DEMO_CLIENT_ID) {
      navigate(`/clients/${client.id}/baseline`);
      return;
    }
    if (client.has_interval_data && client.has_tariff) {
      navigate(`/clients/${client.id}/baseline`);
    } else {
      navigate(`/clients/${client.id}/setup`);
    }
  };

  // Demo first, rest after
  const sortedClients = [...clients].sort((a, b) => {
    if (a.id === DEMO_CLIENT_ID) return -1;
    if (b.id === DEMO_CLIENT_ID) return 1;
    return 0;
  });

  return (
    <div className="p-8" data-testid="client-list-page">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-semibold text-forest-900">Clients</h1>
          <p className="text-sm text-slate-600 mt-1">Manage your client sites and energy analyses</p>
        </div>
        <Link
          to="/clients/new"
          data-testid="new-client-btn"
          className="inline-flex items-center gap-2 bg-lime-500 hover:bg-lime-600 text-forest-900 font-medium rounded-lg px-4 py-2.5 text-sm transition-colors"
        >
          <Plus size={16} />
          New Client
        </Link>
      </div>

      {error && (
        <div className="flex items-start gap-2 bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 mb-6 text-sm">
          <AlertCircle size={16} className="mt-0.5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {loading && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => <SkeletonCard key={i} />)}
        </div>
      )}

      {!loading && !error && clients.length === 0 && (
        <div className="text-center py-20">
          <div className="inline-flex items-center justify-center w-14 h-14 bg-forest-100 rounded-2xl mb-4">
            <Zap size={24} className="text-forest-700" />
          </div>
          <h3 className="text-base font-medium text-forest-900 mb-1">No clients yet</h3>
          <p className="text-sm text-slate-500 mb-6">Add your first client to get started.</p>
          <Link
            to="/clients/new"
            className="inline-flex items-center gap-2 bg-lime-500 hover:bg-lime-600 text-forest-900 font-medium rounded-lg px-4 py-2.5 text-sm transition-colors"
          >
            <Plus size={16} />
            Add first client
          </Link>
        </div>
      )}

      {!loading && sortedClients.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {sortedClients.map((client) => {
            const isDemo = client.id === DEMO_CLIENT_ID;
            return (
              <button
                key={client.id}
                onClick={() => handleCardClick(client)}
                data-testid={`client-card-${client.id}`}
                className={`bg-white rounded-xl shadow-sm p-5 text-left transition-all group border ${
                  isDemo
                    ? 'border-lime-400 hover:border-lime-500 hover:shadow-lg ring-2 ring-lime-200/60'
                    : 'border-slate-200 hover:border-forest-300 hover:shadow-md'
                }`}
              >
                <div className="flex items-start justify-between mb-1 gap-2">
                  <h3 className="font-semibold text-forest-900 group-hover:text-forest-700 transition-colors text-base leading-snug">
                    {client.name}
                  </h3>
                  <div className="flex flex-col items-end gap-1">
                    {isDemo && <DemoBadge />}
                    <StatusBadge status={client.status} />
                  </div>
                </div>

                {client.address && (
                  <p className="flex items-center gap-1 text-xs text-slate-500 mb-1">
                    <MapPin size={11} />
                    {client.address}
                  </p>
                )}
                {client.nmi && (
                  <p className="text-xs text-slate-400 mb-3 font-mono">NMI: {client.nmi}</p>
                )}

                <div className="flex flex-wrap gap-1.5 mb-4">
                  <DataChip present={client.has_interval_data} label="Interval data" />
                  <DataChip present={client.has_tariff} label="Tariff" />
                </div>

                {(client.annual_kwh || client.annual_cost) && (
                  <div className="flex gap-4 pt-3 border-t border-slate-100">
                    {client.annual_kwh && (
                      <div>
                        <p className="text-xs text-slate-500">Annual kWh</p>
                        <p className="text-sm font-semibold text-forest-900 tabnum">
                          {fmtNumber(client.annual_kwh / 1000, 1)} MWh
                        </p>
                      </div>
                    )}
                    {client.annual_cost && (
                      <div>
                        <p className="text-xs text-slate-500">Annual Cost</p>
                        <p className="text-sm font-semibold text-forest-800 tabnum">
                          {fmtCurrency(client.annual_cost)}
                        </p>
                      </div>
                    )}
                  </div>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
