import React, { useState, useCallback } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import {
  ChevronRight,
  CheckCircle,
  Upload,
  AlertCircle,
  Loader,
  FileText,
  Zap,
  Building2,
} from 'lucide-react';
import {
  createClient,
  uploadIntervalData,
  getTariffs,
  setClientTariff,
  fmtCurrency,
  fmtNumber,
} from '../lib/api';

const SITE_TYPES = [
  { value: 'cafe', label: 'Cafe / Coffee Shop' },
  { value: 'office', label: 'Office' },
  { value: 'retail', label: 'Retail' },
  { value: 'industrial', label: 'Industrial' },
  { value: 'hospitality', label: 'Hospitality' },
];

const TARIFF_TYPE_LABELS = {
  tou: 'Time-of-Use',
  flat: 'Flat Rate',
  block: 'Block Rate',
  demand: 'Demand',
};

// Step indicator
function StepIndicator({ step, total }) {
  return (
    <div className="flex items-center gap-2 mb-8">
      {Array.from({ length: total }, (_, i) => i + 1).map((s) => (
        <React.Fragment key={s}>
          <div
            className={`flex items-center justify-center w-7 h-7 rounded-full text-xs font-semibold border-2 transition-colors ${
              s < step
                ? 'bg-indigo-600 border-indigo-600 text-white'
                : s === step
                ? 'border-indigo-600 text-indigo-600 bg-white'
                : 'border-slate-300 text-slate-400 bg-white'
            }`}
          >
            {s < step ? <CheckCircle size={14} /> : s}
          </div>
          {s < total && (
            <div
              className={`flex-1 h-0.5 ${s < step ? 'bg-indigo-600' : 'bg-slate-200'}`}
            />
          )}
        </React.Fragment>
      ))}
      <span className="ml-2 text-xs text-slate-500">Step {step} of {total}</span>
    </div>
  );
}

// Step 1: Site Details
function Step1SiteDetails({ onNext }) {
  const [form, setForm] = useState({
    name: '',
    address: '',
    nmi: '',
    site_type: '',
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleChange = (e) => {
    setForm((f) => ({ ...f, [e.target.name]: e.target.value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (!form.name.trim()) {
      setError('Site name is required.');
      return;
    }
    setLoading(true);
    try {
      const res = await createClient(form);
      onNext(res.data);
    } catch (err) {
      setError(
        err.response?.data?.detail ||
          err.response?.data?.message ||
          'Failed to create client. Please try again.'
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <div>
        <h2 className="text-lg font-semibold text-slate-900">Site Details</h2>
        <p className="text-sm text-slate-500 mt-1">Enter the basic information about this client site.</p>
      </div>

      {error && (
        <div className="flex items-start gap-2 bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
          <AlertCircle size={16} className="mt-0.5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <div>
        <label className="block text-sm font-medium text-slate-700 mb-1.5">
          Client / Site Name <span className="text-red-500">*</span>
        </label>
        <input
          type="text"
          name="name"
          value={form.name}
          onChange={handleChange}
          required
          placeholder="e.g. Acme Coffee Roasters – Sydney CBD"
          className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-slate-700 mb-1.5">
          Street Address
        </label>
        <input
          type="text"
          name="address"
          value={form.address}
          onChange={handleChange}
          placeholder="123 Main St, Sydney NSW 2000"
          className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1.5">
            NMI <span className="text-slate-400 font-normal">(optional)</span>
          </label>
          <input
            type="text"
            name="nmi"
            value={form.nmi}
            onChange={handleChange}
            placeholder="e.g. 4102385731"
            className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent font-mono"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1.5">
            Site Type
          </label>
          <select
            name="site_type"
            value={form.site_type}
            onChange={handleChange}
            className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent bg-white"
          >
            <option value="">Select type…</option>
            {SITE_TYPES.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="pt-2">
        <button
          type="submit"
          disabled={loading}
          className="inline-flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white font-medium rounded-lg px-6 py-2.5 text-sm transition-colors"
        >
          {loading ? (
            <>
              <Loader size={15} className="animate-spin" />
              Creating…
            </>
          ) : (
            <>
              Continue
              <ChevronRight size={16} />
            </>
          )}
        </button>
      </div>
    </form>
  );
}

// Step 2: Upload Interval Data
function Step2Upload({ client, onNext, onSkip }) {
  const [file, setFile] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [summary, setSummary] = useState(null);

  const handleFile = (f) => {
    if (f) {
      setFile(f);
      setSummary(null);
      setError('');
    }
  };

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  }, []);

  const handleUpload = async () => {
    if (!file) return;
    setError('');
    setLoading(true);
    try {
      const res = await uploadIntervalData(client.id, file);
      setSummary(res.data);
    } catch (err) {
      setError(
        err.response?.data?.detail ||
          err.response?.data?.message ||
          'Upload failed. Please check your file format and try again.'
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-semibold text-slate-900">Upload Interval Data</h2>
        <p className="text-sm text-slate-500 mt-1">
          Upload a NEM12 export or simple timestamp/kWh CSV for load profile analysis.
        </p>
      </div>

      {error && (
        <div className="flex items-start gap-2 bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
          <AlertCircle size={16} className="mt-0.5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {!summary ? (
        <>
          {/* Drop zone */}
          <div
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            className={`relative border-2 border-dashed rounded-xl p-10 text-center transition-colors ${
              dragging
                ? 'border-indigo-400 bg-indigo-50'
                : file
                ? 'border-emerald-400 bg-emerald-50'
                : 'border-slate-300 bg-slate-50 hover:border-slate-400'
            }`}
          >
            <input
              type="file"
              accept=".csv,.nem12,.txt"
              onChange={(e) => handleFile(e.target.files[0])}
              className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
            />
            {file ? (
              <div className="space-y-2">
                <FileText size={32} className="mx-auto text-emerald-600" />
                <p className="text-sm font-medium text-emerald-700">{file.name}</p>
                <p className="text-xs text-slate-500">{(file.size / 1024).toFixed(1)} KB — click to change</p>
              </div>
            ) : (
              <div className="space-y-2">
                <Upload size={32} className="mx-auto text-slate-400" />
                <p className="text-sm font-medium text-slate-700">Drop CSV here or click to browse</p>
                <p className="text-xs text-slate-400">NEM12 export or simple timestamp/kWh CSV</p>
              </div>
            )}
          </div>

          {file && (
            <button
              onClick={handleUpload}
              disabled={loading}
              className="inline-flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white font-medium rounded-lg px-6 py-2.5 text-sm transition-colors"
            >
              {loading ? (
                <>
                  <Loader size={15} className="animate-spin" />
                  Uploading…
                </>
              ) : (
                <>
                  <Upload size={15} />
                  Upload
                </>
              )}
            </button>
          )}
        </>
      ) : (
        /* Upload success summary */
        <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-5">
          <div className="flex items-center gap-2 mb-4">
            <CheckCircle size={18} className="text-emerald-600" />
            <span className="text-sm font-semibold text-emerald-800">Upload successful</span>
          </div>
          <div className="grid grid-cols-2 gap-4">
            {summary.intervals_count && (
              <div>
                <p className="text-xs text-emerald-700">Intervals loaded</p>
                <p className="text-lg font-semibold text-emerald-900 tabnum">
                  {summary.intervals_count.toLocaleString()}
                </p>
              </div>
            )}
            {summary.date_range && (
              <div>
                <p className="text-xs text-emerald-700">Date range</p>
                <p className="text-sm font-semibold text-emerald-900">{summary.date_range}</p>
              </div>
            )}
            {summary.annual_kwh && (
              <div>
                <p className="text-xs text-emerald-700">Annual consumption</p>
                <p className="text-lg font-semibold text-emerald-900 tabnum">
                  {fmtNumber(summary.annual_kwh / 1000, 1)} MWh
                </p>
              </div>
            )}
            {summary.peak_kw && (
              <div>
                <p className="text-xs text-emerald-700">Peak demand</p>
                <p className="text-lg font-semibold text-emerald-900 tabnum">
                  {fmtNumber(summary.peak_kw, 1)} kW
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      <div className="flex gap-3 pt-2">
        {summary && (
          <button
            onClick={onNext}
            className="inline-flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white font-medium rounded-lg px-6 py-2.5 text-sm transition-colors"
          >
            Continue
            <ChevronRight size={16} />
          </button>
        )}
        <button
          onClick={onSkip}
          className="inline-flex items-center gap-2 border border-slate-300 text-slate-600 hover:bg-slate-50 font-medium rounded-lg px-6 py-2.5 text-sm transition-colors"
        >
          Skip for now
        </button>
      </div>
    </div>
  );
}

// Step 3: Select Tariff
function Step3Tariff({ client, onFinish }) {
  const [tariffs, setTariffs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selecting, setSelecting] = useState(null);
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState('');

  React.useEffect(() => {
    getTariffs()
      .then((res) => setTariffs(res.data))
      .catch(() => setError('Failed to load tariffs.'))
      .finally(() => setLoading(false));
  }, []);

  const handleSelect = async (tariff) => {
    setSelecting(tariff.id);
    setError('');
    try {
      await setClientTariff(client.id, tariff.id);
      setSelected(tariff);
    } catch (err) {
      setError(
        err.response?.data?.detail ||
          err.response?.data?.message ||
          'Failed to assign tariff.'
      );
    } finally {
      setSelecting(null);
    }
  };

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-semibold text-slate-900">Select Tariff</h2>
        <p className="text-sm text-slate-500 mt-1">
          Choose the applicable network/retail tariff for this site.
        </p>
      </div>

      {error && (
        <div className="flex items-start gap-2 bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
          <AlertCircle size={16} className="mt-0.5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-20 bg-slate-100 rounded-xl animate-pulse" />
          ))}
        </div>
      ) : tariffs.length === 0 ? (
        <p className="text-sm text-slate-500 py-8 text-center">No tariffs available.</p>
      ) : (
        <div className="space-y-3">
          {tariffs.map((t) => (
            <div
              key={t.id}
              className={`border rounded-xl p-4 transition-colors ${
                selected?.id === t.id
                  ? 'border-emerald-400 bg-emerald-50'
                  : 'border-slate-200 bg-white hover:border-slate-300'
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-medium text-slate-900 text-sm">{t.plan_name || t.name}</span>
                    {t.type && (
                      <span className="px-2 py-0.5 bg-slate-100 text-slate-600 rounded-full text-xs">
                        {TARIFF_TYPE_LABELS[t.type] || t.type}
                      </span>
                    )}
                  </div>
                  {t.retailer && (
                    <p className="text-xs text-slate-500 mb-2">{t.retailer}</p>
                  )}
                  <div className="flex flex-wrap gap-3 text-xs text-slate-600">
                    {t.supply_charge_daily != null && (
                      <span>Supply: {fmtCurrency(t.supply_charge_daily * 365)}/yr</span>
                    )}
                    {t.energy_rate_peak != null && (
                      <span>Peak: {(t.energy_rate_peak * 100).toFixed(1)}¢/kWh</span>
                    )}
                    {t.energy_rate_offpeak != null && (
                      <span>Off-peak: {(t.energy_rate_offpeak * 100).toFixed(1)}¢/kWh</span>
                    )}
                    {t.demand_charge != null && (
                      <span className="text-purple-700">Demand: {fmtCurrency(t.demand_charge)}/kW/mo</span>
                    )}
                  </div>
                </div>
                <div className="flex-shrink-0">
                  {selected?.id === t.id ? (
                    <span className="inline-flex items-center gap-1 text-emerald-600 text-sm font-medium">
                      <CheckCircle size={16} />
                      Selected
                    </span>
                  ) : (
                    <button
                      onClick={() => handleSelect(t)}
                      disabled={!!selecting}
                      className="inline-flex items-center gap-1 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white text-xs font-medium rounded-lg px-3 py-1.5 transition-colors"
                    >
                      {selecting === t.id ? (
                        <Loader size={12} className="animate-spin" />
                      ) : null}
                      Select
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="pt-2">
        <button
          onClick={onFinish}
          disabled={!selected}
          className="inline-flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-300 disabled:text-slate-500 text-white font-medium rounded-lg px-6 py-2.5 text-sm transition-colors"
        >
          <Zap size={15} />
          Go to Baseline Analysis
        </button>
      </div>
    </div>
  );
}

export default function ClientSetup() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [client, setClient] = useState(null);

  const handleStep1Next = (createdClient) => {
    setClient(createdClient);
    setStep(2);
  };

  const handleStep2Next = () => setStep(3);
  const handleStep2Skip = () => setStep(3);

  const handleFinish = () => {
    if (client) {
      navigate(`/clients/${client.id}/baseline`);
    }
  };

  return (
    <div className="p-8">
      {/* Header */}
      <div className="flex items-center gap-2 text-sm text-slate-500 mb-6">
        <Link to="/clients" className="hover:text-indigo-600 transition-colors">
          Clients
        </Link>
        <ChevronRight size={14} />
        <span className="text-slate-900 font-medium">New Client</span>
      </div>

      <div className="max-w-xl">
        <div className="mb-2">
          <h1 className="text-2xl font-semibold text-slate-900">New Client Setup</h1>
        </div>

        <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-8 mt-6">
          <StepIndicator step={step} total={3} />

          {step === 1 && <Step1SiteDetails onNext={handleStep1Next} />}
          {step === 2 && client && (
            <Step2Upload
              client={client}
              onNext={handleStep2Next}
              onSkip={handleStep2Skip}
            />
          )}
          {step === 3 && client && (
            <Step3Tariff client={client} onFinish={handleFinish} />
          )}
        </div>
      </div>
    </div>
  );
}
