import React, { useState, useCallback } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import {
  ChevronRight, CheckCircle, Upload, AlertCircle, Loader, FileText, Zap,
} from 'lucide-react';
import {
  createClient, uploadIntervalData, getTariffs, setClientTariff, fmtCurrency, fmtNumber,
} from '../lib/api';

const SITE_TYPES = [
  { value: 'cafe', label: 'Cafe / Coffee Shop' },
  { value: 'office', label: 'Office' },
  { value: 'retail', label: 'Retail' },
  { value: 'industrial', label: 'Industrial' },
  { value: 'hospitality', label: 'Hospitality' },
];

function StepIndicator({ step, total }) {
  return (
    <div className="flex items-center gap-2 mb-8">
      {Array.from({ length: total }, (_, i) => i + 1).map((s) => (
        <React.Fragment key={s}>
          <div
            className={`flex items-center justify-center w-7 h-7 rounded-full text-xs font-semibold border-2 transition-colors ${
              s < step ? 'bg-violet border-violet text-white'
              : s === step ? 'border-violet text-violet bg-cream-50'
              : 'border-line text-ink-mute bg-cream-50'
            }`}
          >
            {s < step ? <CheckCircle size={14} /> : s}
          </div>
          {s < total && (<div className={`flex-1 h-0.5 ${s < step ? 'bg-violet' : 'bg-line'}`} />)}
        </React.Fragment>
      ))}
      <span className="ml-2 text-[11px] text-ink-mute uppercase tracking-wider">Step {step}/{total}</span>
    </div>
  );
}

function Step1SiteDetails({ onNext }) {
  const [form, setForm] = useState({ name: '', address: '', nmi: '', site_type: 'cafe' });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (!form.name.trim()) { setError('Site name is required.'); return; }
    setLoading(true);
    try {
      const res = await createClient(form);
      onNext(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create client.');
    } finally { setLoading(false); }
  };

  const inputCls = "w-full border border-line rounded-lg px-3 py-2.5 text-sm bg-cream-50 text-forest-900 placeholder-ink-mute focus:outline-none focus:ring-2 focus:ring-violet/40 focus:border-violet";

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <div>
        <h2 className="font-display text-2xl text-forest-900">Site details</h2>
        <p className="text-sm text-ink-mute mt-1">Where is this site and what kind of business is it?</p>
      </div>
      {error && (
        <div className="flex items-start gap-2 bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
          <AlertCircle size={16} className="mt-0.5 flex-shrink-0" /><span>{error}</span>
        </div>
      )}
      <div>
        <label className="block text-xs uppercase tracking-wider text-ink-mute mb-1.5">Client / Site Name *</label>
        <input type="text" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required
               placeholder="e.g. Acme Coffee Roasters – Sydney" className={inputCls}
               data-testid="setup-name-input" />
      </div>
      <div>
        <label className="block text-xs uppercase tracking-wider text-ink-mute mb-1.5">Street Address</label>
        <input type="text" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })}
               placeholder="123 Main St, Sydney NSW 2000" className={inputCls} />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-xs uppercase tracking-wider text-ink-mute mb-1.5">NMI (optional)</label>
          <input type="text" value={form.nmi} onChange={(e) => setForm({ ...form, nmi: e.target.value })}
                 placeholder="e.g. 6305987412" className={`${inputCls} font-mono`} />
        </div>
        <div>
          <label className="block text-xs uppercase tracking-wider text-ink-mute mb-1.5">Site Type</label>
          <select value={form.site_type} onChange={(e) => setForm({ ...form, site_type: e.target.value })} className={inputCls}>
            {SITE_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
        </div>
      </div>
      <div className="pt-2">
        <button type="submit" disabled={loading} data-testid="setup-step1-next"
                className="btn-violet inline-flex items-center gap-2 font-semibold rounded-full px-6 py-2.5 text-sm transition-all disabled:opacity-50">
          {loading ? <><Loader size={14} className="animate-spin" /> Creating…</> : <>Continue <ChevronRight size={15} /></>}
        </button>
      </div>
    </form>
  );
}

function Step2Upload({ client, onNext, onSkip }) {
  const [file, setFile] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [summary, setSummary] = useState(null);

  const handleDrop = useCallback((e) => {
    e.preventDefault(); setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) { setFile(f); setSummary(null); setError(''); }
  }, []);

  const handleUpload = async () => {
    if (!file) return;
    setError(''); setLoading(true);
    try {
      const res = await uploadIntervalData(client.id, file);
      setSummary(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Upload failed.');
    } finally { setLoading(false); }
  };

  return (
    <div className="space-y-5">
      <div>
        <h2 className="font-display text-2xl text-forest-900">Interval data</h2>
        <p className="text-sm text-ink-mute mt-1">NEM12 or simple timestamp/kWh CSV. Skip to use a synthetic baseline.</p>
      </div>
      {error && (
        <div className="flex items-start gap-2 bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
          <AlertCircle size={16} className="mt-0.5 flex-shrink-0" /><span>{error}</span>
        </div>
      )}
      {!summary ? (
        <>
          <div
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            className={`relative border-2 border-dashed rounded-xl p-10 text-center transition-colors ${
              dragging ? 'border-violet bg-violet/5'
              : file ? 'border-lime bg-lime/10'
              : 'border-line bg-cream-50 hover:border-forest-300'
            }`}
          >
            <input type="file" accept=".csv,.nem12,.txt" onChange={(e) => { setFile(e.target.files[0]); setSummary(null); setError(''); }}
                   className="absolute inset-0 w-full h-full opacity-0 cursor-pointer" />
            {file ? (
              <div className="space-y-2">
                <FileText size={32} className="mx-auto text-forest-700" />
                <p className="text-sm font-medium text-forest-800">{file.name}</p>
                <p className="text-[11px] text-ink-mute">{(file.size / 1024).toFixed(1)} KB · click to change</p>
              </div>
            ) : (
              <div className="space-y-2">
                <Upload size={28} className="mx-auto text-ink-mute" />
                <p className="text-sm font-medium text-forest-800">Drop CSV here or click to browse</p>
              </div>
            )}
          </div>
          {file && (
            <button onClick={handleUpload} disabled={loading} data-testid="setup-upload-btn"
                    className="btn-violet inline-flex items-center gap-2 font-semibold rounded-full px-6 py-2.5 text-sm transition-all disabled:opacity-50">
              {loading ? <><Loader size={14} className="animate-spin" /> Uploading…</> : <><Upload size={14} /> Upload</>}
            </button>
          )}
        </>
      ) : (
        <div className="bg-lime/10 border border-lime/40 rounded-xl p-5">
          <div className="flex items-center gap-2 mb-3">
            <CheckCircle size={16} className="text-forest-700" />
            <span className="text-sm font-semibold text-forest-800">Upload successful</span>
          </div>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div><p className="text-[10px] uppercase text-ink-mute">Intervals</p><p className="text-base font-semibold text-forest-900 tabnum">{summary.intervals_count?.toLocaleString()}</p></div>
            <div><p className="text-[10px] uppercase text-ink-mute">Annual</p><p className="text-base font-semibold text-forest-900 tabnum">{fmtNumber((summary.annual_kwh || 0) / 1000, 1)} MWh</p></div>
            <div><p className="text-[10px] uppercase text-ink-mute">Peak kW</p><p className="text-base font-semibold text-forest-900 tabnum">{fmtNumber(summary.peak_kw || 0, 1)} kW</p></div>
          </div>
        </div>
      )}
      <div className="flex gap-3 pt-2">
        {summary && (
          <button onClick={onNext} data-testid="setup-step2-next"
                  className="btn-violet inline-flex items-center gap-2 font-semibold rounded-full px-6 py-2.5 text-sm transition-all">
            Continue <ChevronRight size={15} />
          </button>
        )}
        <button onClick={onSkip} data-testid="setup-step2-skip"
                className="inline-flex items-center gap-2 border border-line text-ink-soft hover:bg-cream-100 font-medium rounded-full px-6 py-2.5 text-sm transition-colors">
          Skip
        </button>
      </div>
    </div>
  );
}

function Step3Tariff({ client, onFinish }) {
  const [tariffs, setTariffs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selecting, setSelecting] = useState(null);
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState('');

  React.useEffect(() => {
    getTariffs().then((res) => setTariffs(res.data))
      .catch(() => setError('Failed to load tariffs.'))
      .finally(() => setLoading(false));
  }, []);

  const handleSelect = async (tariff) => {
    setSelecting(tariff.id); setError('');
    try {
      await setClientTariff(client.id, tariff.id);
      setSelected(tariff);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to assign tariff.');
    } finally { setSelecting(null); }
  };

  return (
    <div className="space-y-5">
      <div>
        <h2 className="font-display text-2xl text-forest-900">Tariff</h2>
        <p className="text-sm text-ink-mute mt-1">Which retailer plan is the site on today?</p>
      </div>
      {error && (
        <div className="flex items-start gap-2 bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
          <AlertCircle size={16} className="mt-0.5 flex-shrink-0" /><span>{error}</span>
        </div>
      )}
      {loading ? (
        <div className="space-y-3">{[1, 2, 3].map((i) => <div key={i} className="h-20 bg-cream-200 rounded-xl animate-pulse" />)}</div>
      ) : (
        <div className="space-y-3">
          {tariffs.map((t) => (
            <div key={t.id} data-testid={`tariff-${t.id}`}
                 className={`border rounded-xl p-4 transition-colors ${
                   selected?.id === t.id ? 'border-lime bg-lime/10' : 'border-line bg-cream-50 hover:border-forest-300'
                 }`}>
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-semibold text-forest-900 text-sm">{t.plan_name}</span>
                    <span className="px-2 py-0.5 bg-cream-200 text-ink-soft rounded-full text-[10px] uppercase tracking-wider">{t.type}</span>
                  </div>
                  <p className="text-xs text-ink-mute mb-2">{t.retailer} · {t.state}</p>
                  <div className="flex flex-wrap gap-3 text-[11px] text-ink-soft">
                    <span>Supply <span className="tabnum">{fmtCurrency(t.supply_charge * 365)}/yr</span></span>
                    {t.energy_rates?.peak != null && <span>Peak <span className="tabnum">{(t.energy_rates.peak * 100).toFixed(1)}¢</span></span>}
                    {t.energy_rates?.offpeak != null && <span>Off-peak <span className="tabnum">{(t.energy_rates.offpeak * 100).toFixed(1)}¢</span></span>}
                  </div>
                </div>
                <div className="flex-shrink-0">
                  {selected?.id === t.id ? (
                    <span className="inline-flex items-center gap-1 text-forest-700 text-xs font-medium"><CheckCircle size={14} /> Selected</span>
                  ) : (
                    <button onClick={() => handleSelect(t)} disabled={!!selecting} data-testid={`select-tariff-${t.id}`}
                            className="btn-violet inline-flex items-center gap-1 text-xs font-medium rounded-full px-3 py-1.5 transition-colors">
                      {selecting === t.id ? <Loader size={11} className="animate-spin" /> : 'Select'}
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
      <div className="pt-2">
        <button onClick={onFinish} disabled={!selected} data-testid="setup-finish"
                className="btn-violet inline-flex items-center gap-2 font-semibold rounded-full px-6 py-2.5 text-sm transition-all disabled:opacity-50">
          <Zap size={14} /> Open Baseline
        </button>
      </div>
    </div>
  );
}

export default function ClientSetup() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [client, setClient] = useState(null);

  return (
    <div className="p-10 max-w-3xl" data-testid="client-setup-page">
      <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.15em] text-ink-mute mb-3">
        <Link to="/clients" className="hover:text-forest-700">Clients</Link>
        <ChevronRight size={12} />
        <span className="text-violet font-medium">New client</span>
      </div>
      <h1 className="font-display text-5xl text-forest-900 leading-none mb-8">New client setup.</h1>

      <div className="bg-cream-50 border border-line rounded-2xl shadow-card p-8">
        <StepIndicator step={step} total={3} />
        {step === 1 && <Step1SiteDetails onNext={(c) => { setClient(c); setStep(2); }} />}
        {step === 2 && client && <Step2Upload client={client} onNext={() => setStep(3)} onSkip={() => setStep(3)} />}
        {step === 3 && client && <Step3Tariff client={client} onFinish={() => navigate(`/clients/${client.id}/baseline`)} />}
      </div>
    </div>
  );
}
