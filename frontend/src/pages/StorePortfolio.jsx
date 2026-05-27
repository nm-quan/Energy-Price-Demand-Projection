import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  ChevronRight, MapPin, Zap, DollarSign, Check, Loader, AlertCircle,
  BarChart3, Layers, Trash2, Store, CheckSquare, X,
} from 'lucide-react';
import { getClient, listStores, deleteStore, getStoreBaseline, getAggregateBaseline, fmtCurrency, fmtNumber } from '../lib/api';

const SITE_TYPE_STYLE = {
  cafe:        { label: 'Café',        bg: 'bg-amber-100',  text: 'text-amber-800',  border: 'border-amber-200'  },
  retail:      { label: 'Retail',      bg: 'bg-blue-100',   text: 'text-blue-800',   border: 'border-blue-200'   },
  office:      { label: 'Office',      bg: 'bg-violet-100', text: 'text-violet-800', border: 'border-violet-200' },
  industrial:  { label: 'Industrial',  bg: 'bg-slate-100',  text: 'text-slate-800',  border: 'border-slate-200'  },
  hospitality: { label: 'Hospitality', bg: 'bg-rose-100',   text: 'text-rose-800',   border: 'border-rose-200'   },
};

function SiteTypeBadge({ type }) {
  const s = SITE_TYPE_STYLE[type?.toLowerCase()] || { label: type || '—', bg: 'bg-cream-200', text: 'text-ink-mute', border: 'border-line' };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider border ${s.bg} ${s.text} ${s.border}`}>
      {s.label}
    </span>
  );
}

function StoreCard({ store, selectionMode, selected, onToggle, onDelete, onClick }) {
  return (
    <div
      data-testid={`store-card-${store.id}`}
      onClick={selectionMode ? onToggle : onClick}
      className={`group relative bg-cream-50 border rounded-2xl p-5 transition-all cursor-pointer ${
        selectionMode && selected
          ? 'border-violet ring-2 ring-violet/30 bg-violet/5'
          : selectionMode
          ? 'border-line hover:border-violet/50'
          : 'border-line hover:shadow-card hover:border-forest-300'
      }`}
    >
      {/* Selection checkbox (only in selection mode) */}
      {selectionMode && (
        <div className={`absolute top-4 right-4 w-5 h-5 rounded border-2 flex items-center justify-center transition-colors ${
          selected ? 'bg-violet border-violet' : 'bg-cream-50 border-line'
        }`}>
          {selected && <Check size={11} strokeWidth={3} className="text-white" />}
        </div>
      )}

      {/* Store name + badge */}
      <div className={`mb-3 ${selectionMode ? 'pr-8' : 'pr-4'}`}>
        <div className="flex items-center gap-2 mb-1">
          <SiteTypeBadge type={store.site_type} />
        </div>
        <h3 className="font-display text-xl text-forest-900 leading-tight">{store.name}</h3>
      </div>

      {/* Address */}
      {store.address && (
        <p className="flex items-start gap-1.5 text-xs text-ink-mute mb-3 leading-relaxed">
          <MapPin size={12} className="mt-0.5 flex-shrink-0 text-ink-mute/70" />
          {store.address}
        </p>
      )}

      {/* Stats row */}
      <div className="flex items-center gap-4 pt-3 border-t border-line">
        {store.annual_kwh && (
          <div className="flex items-center gap-1.5">
            <Zap size={12} className="text-amber-500 flex-shrink-0" />
            <span className="text-xs font-semibold text-forest-800 tabnum">
              {fmtNumber(store.annual_kwh / 1000, 1)} MWh/yr
            </span>
          </div>
        )}
        {store.annual_cost && (
          <div className="flex items-center gap-1.5">
            <DollarSign size={12} className="text-forest-600 flex-shrink-0" />
            <span className="text-xs font-semibold text-forest-800 tabnum">
              {fmtCurrency(store.annual_cost)}/yr
            </span>
          </div>
        )}
        {store.nmi && (
          <span className="ml-auto text-[10px] text-ink-mute tabnum">NMI {store.nmi}</span>
        )}
      </div>

      {/* Delete button — only in normal mode */}
      {!selectionMode && (
        <button
          type="button"
          data-testid={`delete-store-${store.id}`}
          onClick={(e) => { e.stopPropagation(); onDelete(store.id); }}
          className="absolute bottom-3 right-3 opacity-0 group-hover:opacity-100 transition-opacity text-ink-mute hover:text-red-600 p-1 rounded"
        >
          <Trash2 size={13} />
        </button>
      )}
    </div>
  );
}

export default function StorePortfolio() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [client,        setClient]        = useState(null);
  const [stores,        setStores]        = useState([]);
  const [loading,       setLoading]       = useState(true);
  const [analysing,     setAnalysing]     = useState(false);
  const [error,         setError]         = useState('');
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedIds,   setSelectedIds]   = useState(new Set());

  useEffect(() => {
    if (!id) return;
    (async () => {
      setLoading(true);
      setError('');
      try {
        const [clientRes, storesRes] = await Promise.all([getClient(id), listStores(id)]);
        setClient(clientRes.data);
        sessionStorage.setItem(`client_name_${id}`, clientRes.data.name);
        setStores(storesRes.data || []);
      } catch (err) {
        setError(err.response?.data?.detail || 'Failed to load portfolio.');
      } finally {
        setLoading(false);
      }
    })();
  }, [id]);

  const toggleStore = (storeId) => {
    setSelectedIds((cur) => {
      const next = new Set(cur);
      if (next.has(storeId)) next.delete(storeId); else next.add(storeId);
      return next;
    });
  };

  const handleClickStore = async (store) => {
    setAnalysing(true);
    setError('');
    try {
      const res = await getStoreBaseline(id, store.id);
      sessionStorage.setItem(
        `store_context_${id}`,
        JSON.stringify({
          type: 'single',
          store_ids: [store.id],
          store_names: [store.name],
          baseline: res.data,
        })
      );
      navigate(`/clients/${id}/baseline`);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load store baseline.');
      setAnalysing(false);
    }
  };

  const handleDeleteStore = async (storeId) => {
    try {
      await deleteStore(id, storeId);
      setStores((cur) => cur.filter((s) => s.id !== storeId));
      setSelectedIds((cur) => { const next = new Set(cur); next.delete(storeId); return next; });
    } catch {
      setError('Failed to delete store.');
    }
  };

  const handleAnalyseSelected = async () => {
    if (selectedIds.size === 0) return;
    setAnalysing(true);
    setError('');
    try {
      const storeIdList    = Array.from(selectedIds);
      const selectedStores = stores.filter((s) => selectedIds.has(s.id));
      const storeNames     = selectedStores.map((s) => s.name);

      let baseline;
      if (storeIdList.length === 1) {
        const res = await getStoreBaseline(id, storeIdList[0]);
        baseline = res.data;
      } else {
        const res = await getAggregateBaseline(id, storeIdList);
        baseline = res.data;
      }

      sessionStorage.setItem(
        `store_context_${id}`,
        JSON.stringify({
          type: storeIdList.length === 1 ? 'single' : 'aggregate',
          store_ids: storeIdList,
          store_names: storeNames,
          baseline,
        })
      );
      navigate(`/clients/${id}/baseline`);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load analysis. Try again.');
      setAnalysing(false);
    }
  };

  const exitSelectionMode = () => {
    setSelectionMode(false);
    setSelectedIds(new Set());
  };

  const selectedCount = selectedIds.size;
  const totalKwh  = stores.filter((s) => selectedIds.has(s.id)).reduce((a, s) => a + (s.annual_kwh || 0), 0);
  const totalCost = stores.filter((s) => selectedIds.has(s.id)).reduce((a, s) => a + (s.annual_cost || 0), 0);

  return (
    <div className="p-10 max-w-7xl" data-testid="portfolio-page">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.15em] text-ink-mute mb-3">
        <Link to="/clients" className="hover:text-forest-700">Clients</Link>
        <ChevronRight size={12} />
        <span className="text-violet font-medium">Portfolio</span>
      </div>

      {/* Header */}
      {client && (
        <div className="flex items-end justify-between mb-8 gap-4">
          <div>
            <h1 className="font-display text-5xl text-forest-900 leading-none">{client.name}</h1>
            <p className="text-sm text-ink-soft mt-2">
              {selectionMode
                ? 'Select stores to compare or aggregate their load profiles.'
                : 'Click a store to open its dashboard, or use Select to group stores.'}
            </p>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            {selectionMode ? (
              <button
                type="button"
                onClick={exitSelectionMode}
                className="inline-flex items-center gap-1.5 text-xs text-ink-mute hover:text-red-600 border border-line rounded-full px-3 py-1.5 transition-colors"
              >
                <X size={12} /> Cancel
              </button>
            ) : (
              <button
                type="button"
                data-testid="select-stores-btn"
                onClick={() => setSelectionMode(true)}
                className="inline-flex items-center gap-1.5 text-xs text-forest-700 hover:text-violet border border-line hover:border-violet rounded-full px-3 py-1.5 transition-colors"
              >
                <CheckSquare size={13} /> Select stores
              </button>
            )}
          </div>
        </div>
      )}

      {error && (
        <div className="flex items-start gap-2 bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm mb-6">
          <AlertCircle size={16} className="mt-0.5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {loading && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-44 bg-cream-100 rounded-2xl animate-pulse" />
          ))}
        </div>
      )}

      {!loading && stores.length === 0 && (
        <div className="border-2 border-dashed border-line rounded-2xl bg-cream-50 p-12 text-center">
          <div className="inline-flex items-center justify-center w-12 h-12 bg-lime/40 rounded-xl mb-4">
            <Store size={20} className="text-forest-800" />
          </div>
          <h3 className="font-display text-xl text-forest-900 mb-1">No stores yet.</h3>
          <p className="text-sm text-ink-mute">Add stores to start analysing this client's portfolio.</p>
        </div>
      )}

      {!loading && stores.length > 0 && (
        <>
          <div className="flex items-center justify-between mb-4">
            <p className="text-xs text-ink-mute">
              <span className="font-semibold text-forest-800">{stores.length}</span> store{stores.length !== 1 ? 's' : ''}
              {selectionMode && (
                <> · <span className="font-semibold text-violet">{selectedCount}</span> selected</>
              )}
            </p>
            {selectionMode && (
              <button
                type="button"
                onClick={() =>
                  selectedCount === stores.length
                    ? setSelectedIds(new Set())
                    : setSelectedIds(new Set(stores.map((s) => s.id)))
                }
                className="text-xs text-violet hover:text-violet-700 font-medium"
              >
                {selectedCount === stores.length ? 'Deselect all' : 'Select all'}
              </button>
            )}
          </div>

          {analysing && (
            <div className="flex items-center gap-2 text-xs text-ink-mute mb-4">
              <Loader size={13} className="animate-spin text-violet" /> Loading baseline…
            </div>
          )}

          <div className={`grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 ${selectionMode ? 'pb-32' : ''}`}>
            {stores.map((store) => (
              <StoreCard
                key={store.id}
                store={store}
                selectionMode={selectionMode}
                selected={selectedIds.has(store.id)}
                onToggle={() => toggleStore(store.id)}
                onDelete={handleDeleteStore}
                onClick={() => handleClickStore(store)}
              />
            ))}
          </div>
        </>
      )}

      {/* Sticky action bar — only in selection mode with stores selected */}
      {selectionMode && selectedCount > 0 && (
        <div className="fixed bottom-0 left-60 right-0 z-20 px-10 py-4 bg-cream-50/90 border-t border-line backdrop-blur-sm">
          <div className="max-w-7xl mx-auto flex items-center justify-between gap-6">
            <div className="flex items-center gap-6">
              {selectedCount === 1 ? (
                <p className="text-sm font-semibold text-forest-900">
                  {stores.find((s) => selectedIds.has(s.id))?.name}
                </p>
              ) : (
                <div className="flex items-center gap-3">
                  <Layers size={15} className="text-violet flex-shrink-0" />
                  <p className="text-sm font-semibold text-forest-900">
                    {selectedCount} stores selected
                  </p>
                </div>
              )}
              {totalKwh > 0 && (
                <span className="text-xs text-ink-mute tabnum">
                  {fmtNumber(totalKwh / 1000, 1)} MWh/yr ·{' '}
                  <span className="text-forest-700 font-medium">{fmtCurrency(totalCost)}/yr</span>
                </span>
              )}
            </div>

            <button
              type="button"
              onClick={handleAnalyseSelected}
              disabled={analysing}
              data-testid="analyse-selection-btn"
              className="btn-violet inline-flex items-center gap-2 font-semibold rounded-full px-6 py-2.5 text-sm transition-all disabled:opacity-50"
            >
              {analysing ? (
                <><Loader size={14} className="animate-spin" /> Loading…</>
              ) : selectedCount === 1 ? (
                <><BarChart3 size={14} /> View Baseline</>
              ) : (
                <><Layers size={14} /> Aggregate {selectedCount} stores</>
              )}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
