import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Plus, MapPin, Zap, CheckCircle, XCircle, AlertCircle, ArrowRight } from 'lucide-react';
import { getClients, fmtCurrency, fmtNumber } from '../lib/api';

function StatusBadge({ status }) {
  const styles = {
    draft: 'bg-cream-300 text-ink-soft',
    active: 'bg-lime/30 text-forest-900',
    quoted: 'bg-violet-100 text-violet-700',
  };
  const cls = styles[status?.toLowerCase()] || styles.draft;
  const label = status ? status.charAt(0).toUpperCase() + status.slice(1).toLowerCase() : 'Draft';
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider ${cls}`}>
      {label}
    </span>
  );
}

function DataChip({ present, label }) {
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] ${
        present ? 'bg-forest-50 text-forest-700 border border-forest-100' : 'bg-cream-200 text-ink-mute border border-line'
      }`}
    >
      {present ? <CheckCircle size={10} /> : <XCircle size={10} />}
      {label}
    </span>
  );
}

function SkeletonCard() {
  return (
    <div className="bg-cream-50 border border-line rounded-2xl shadow-card p-6 animate-pulse">
      <div className="h-5 bg-cream-300 rounded w-2/3 mb-3" />
      <div className="h-3 bg-cream-200 rounded w-full mb-2" />
      <div className="h-3 bg-cream-200 rounded w-1/2 mb-4" />
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
    if (client.has_interval_data && client.has_tariff) {
      navigate(`/clients/${client.id}/portfolio`);
    } else {
      navigate(`/clients/${client.id}/setup`);
    }
  };

  return (
    <div className="p-10 max-w-6xl" data-testid="client-list-page">
      <div className="flex items-end justify-between mb-10">
        <div>
          <p className="text-[11px] uppercase tracking-[0.2em] text-ink-mute mb-2">Energy broker workspace</p>
          <h1 className="font-display text-5xl text-forest-900 leading-none">Your clients.</h1>
          <p className="text-sm text-ink-soft mt-3 max-w-md">
            Each card is a site. Pick one to see its load shape, run scenarios, and build savings reports.
          </p>
        </div>
        <Link
          to="/clients/new"
          data-testid="new-client-btn"
          className="btn-violet inline-flex items-center gap-2 font-semibold rounded-full px-5 py-2.5 text-sm transition-all"
        >
          <Plus size={16} strokeWidth={2.5} />
          New Client
        </Link>
      </div>

      {error && (
        <div className="flex items-start gap-2 bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 mb-6 text-sm">
          <AlertCircle size={16} className="mt-0.5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {loading && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
          {[1, 2, 3].map((i) => <SkeletonCard key={i} />)}
        </div>
      )}

      {!loading && !error && clients.length === 0 && (
        <div className="text-center py-24 border-2 border-dashed border-line rounded-3xl bg-cream-50">
          <div className="inline-flex items-center justify-center w-14 h-14 bg-lime/30 rounded-2xl mb-4">
            <Zap size={22} className="text-forest-800" />
          </div>
          <h3 className="font-display text-2xl text-forest-900 mb-1">No clients yet.</h3>
          <p className="text-sm text-ink-mute mb-6">Spin up your first one — it takes about 90 seconds.</p>
          <Link
            to="/clients/new"
            data-testid="empty-state-new-client"
            className="btn-violet inline-flex items-center gap-2 font-semibold rounded-full px-5 py-2.5 text-sm transition-all"
          >
            <Plus size={16} strokeWidth={2.5} />
            Add first client
          </Link>
        </div>
      )}

      {!loading && clients.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
          {clients.map((client) => (
            <button
              key={client.id}
              onClick={() => handleCardClick(client)}
              data-testid={`client-card-${client.id}`}
              className="bg-cream-50 rounded-2xl shadow-card p-6 text-left transition-all group border border-line hover:border-forest-700 hover:-translate-y-0.5 hover:shadow-lg"
            >
              <div className="flex items-start justify-between mb-1 gap-2">
                <h3 className="font-display text-xl text-forest-900 group-hover:text-violet leading-tight">
                  {client.name}
                </h3>
                <StatusBadge status={client.status} />
              </div>

              {client.address && (
                <p className="flex items-center gap-1.5 text-xs text-ink-mute mt-1">
                  <MapPin size={11} />
                  {client.address}
                </p>
              )}
              {client.nmi && (
                <p className="text-[11px] text-ink-mute mt-1 font-mono">NMI · {client.nmi}</p>
              )}

              <div className="flex flex-wrap gap-1.5 mt-4 mb-4">
                <DataChip present={client.has_interval_data} label="Interval data" />
                <DataChip present={client.has_tariff} label="Tariff" />
              </div>

              {(client.annual_kwh || client.annual_cost) && (
                <div className="flex gap-6 pt-4 border-t border-line">
                  {client.annual_kwh && (
                    <div>
                      <p className="text-[10px] uppercase tracking-wider text-ink-mute">Annual</p>
                      <p className="text-base font-semibold text-forest-900 tabnum">
                        {fmtNumber(client.annual_kwh / 1000, 1)} <span className="text-xs font-normal text-ink-mute">MWh</span>
                      </p>
                    </div>
                  )}
                  {client.annual_cost && (
                    <div>
                      <p className="text-[10px] uppercase tracking-wider text-ink-mute">Cost</p>
                      <p className="text-base font-semibold text-violet tabnum">{fmtCurrency(client.annual_cost)}</p>
                    </div>
                  )}
                </div>
              )}

              <div className="mt-4 inline-flex items-center gap-1 text-xs font-medium text-forest-700 group-hover:text-violet transition-colors">
                Open <ArrowRight size={12} className="group-hover:translate-x-1 transition-transform" />
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
