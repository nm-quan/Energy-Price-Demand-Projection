import React, { useState, useEffect, useRef } from 'react';
import { useParams, Link, useSearchParams } from 'react-router-dom';
import {
  ChevronRight, Download, AlertCircle, Loader, FileText, Trash2, Calendar, Plus,
} from 'lucide-react';
import {
  getClient, listReports, getReport, deleteReport, fmtCurrency, fmtNumber, fmtPct,
} from '../lib/api';
import StackedAreaChart from '../components/StackedAreaChart';

// ── PDF export via jspdf + html2canvas (loaded lazily) ─────────────────────
async function exportPdf(node, filename) {
  const [{ default: jsPDF }, { default: html2canvas }] = await Promise.all([
    import('jspdf'),
    import('html2canvas'),
  ]);
  const canvas = await html2canvas(node, { scale: 2, backgroundColor: '#ffffff', useCORS: true });
  const imgData = canvas.toDataURL('image/png');
  const pdf = new jsPDF('p', 'pt', 'a4');
  const pdfW = pdf.internal.pageSize.getWidth();
  const pdfH = pdf.internal.pageSize.getHeight();
  const imgW = pdfW - 40;
  const imgH = (canvas.height * imgW) / canvas.width;
  let heightLeft = imgH;
  let position = 20;
  pdf.addImage(imgData, 'PNG', 20, position, imgW, imgH);
  heightLeft -= pdfH - 40;
  while (heightLeft > 0) {
    position = heightLeft - imgH + 20;
    pdf.addPage();
    pdf.addImage(imgData, 'PNG', 20, position, imgW, imgH);
    heightLeft -= pdfH - 40;
  }
  pdf.save(filename);
}

// ── Saved report rendering ─────────────────────────────────────────────────
function ReportDocument({ report, innerRef }) {
  const baseline = report.baseline || {};
  const shape = baseline.shape_metrics || {};
  const cost = baseline.cost_stack || {};
  const scenarios = report.scenarios || [];
  const tariff = report.tariff || {};
  const generatedAt = new Date(report.created_at).toLocaleDateString('en-AU', {
    day: 'numeric', month: 'long', year: 'numeric',
  });
  const totalLow = scenarios.reduce((s, sc) => s + (sc.savings_annual_low || 0), 0);
  const totalHigh = scenarios.reduce((s, sc) => s + (sc.savings_annual_high || 0), 0);

  return (
    <div ref={innerRef} className="bg-white rounded-2xl overflow-hidden print-page" style={{ maxWidth: 820 }}>
      {/* Cover */}
      <div className="bg-forest-800 text-white px-10 py-12">
        <div className="flex items-center gap-2 mb-8">
          <div className="bg-lime rounded-md w-7 h-7 flex items-center justify-center">
            <FileText size={14} className="text-forest-900" strokeWidth={2.5} />
          </div>
          <span className="font-display text-xl">EnergyScope</span>
        </div>
        <p className="text-[11px] uppercase tracking-[0.2em] text-lime/80 mb-2">Energy Analysis Report</p>
        <h1 className="font-display text-4xl leading-tight">{report.title}</h1>
        <div className="mt-6 pt-6 border-t border-forest-700 text-sm">
          <p className="font-semibold">{report.client.name}</p>
          {report.client.address && <p className="text-forest-100/70 text-xs mt-1">{report.client.address}</p>}
          {report.client.nmi && <p className="text-forest-100/50 text-[11px] mt-1 font-mono">NMI · {report.client.nmi}</p>}
          <p className="text-forest-100/60 text-xs mt-4">Generated {generatedAt}</p>
        </div>
      </div>

      <div className="p-10 space-y-10 text-ink">
        {/* Executive Summary */}
        <section>
          <h2 className="text-[11px] uppercase tracking-widest text-ink-mute mb-3">Executive summary</h2>
          <div className="bg-violet/5 border border-violet/30 rounded-2xl p-5 text-sm leading-relaxed">
            <p>
              The site consumes <strong className="text-violet">{fmtNumber((shape.annual_kwh || 0) / 1000, 1)} MWh</strong> annually
              at a peak demand of <strong className="text-violet">{fmtNumber(shape.peak_kw || 0, 1)} kW</strong>.
              {scenarios.length > 0 && (
                <>
                  {' '}Across {scenarios.length} recommended scenario{scenarios.length === 1 ? '' : 's'}, projected savings are{' '}
                  <strong className="text-violet">{fmtCurrency(totalLow)}–{fmtCurrency(totalHigh)}</strong> per year.
                </>
              )}
            </p>
          </div>
        </section>

        {/* Current tariff */}
        <section>
          <h2 className="text-[11px] uppercase tracking-widest text-ink-mute mb-3">Current tariff</h2>
          <div className="border border-line rounded-xl p-4 text-sm">
            <p className="font-semibold text-forest-900">{tariff.retailer} · {tariff.plan_name}</p>
            <div className="grid grid-cols-3 gap-4 mt-3 text-xs">
              <div><span className="text-ink-mute">Peak</span><br /><span className="tabnum text-forest-800 font-medium">{(tariff.energy_rates?.peak * 100 || 0).toFixed(1)} ¢/kWh</span></div>
              <div><span className="text-ink-mute">Shoulder</span><br /><span className="tabnum text-forest-800 font-medium">{(tariff.energy_rates?.shoulder * 100 || 0).toFixed(1)} ¢/kWh</span></div>
              <div><span className="text-ink-mute">Off-peak</span><br /><span className="tabnum text-forest-800 font-medium">{(tariff.energy_rates?.offpeak * 100 || 0).toFixed(1)} ¢/kWh</span></div>
            </div>
          </div>
        </section>

        {/* Cost breakdown */}
        <section>
          <h2 className="text-[11px] uppercase tracking-widest text-ink-mute mb-3">Baseline cost breakdown</h2>
          <table className="w-full text-sm border border-line rounded-lg overflow-hidden">
            <thead className="bg-cream-200">
              <tr>
                <th className="text-left px-3 py-2 text-[10px] uppercase tracking-wider text-ink-mute">Line item</th>
                <th className="text-right px-3 py-2 text-[10px] uppercase tracking-wider text-ink-mute">Annual</th>
              </tr>
            </thead>
            <tbody>
              {[
                ['Energy — Peak', cost.energy_peak],
                ['Energy — Shoulder', cost.energy_shoulder],
                ['Energy — Off-peak', cost.energy_offpeak],
                ['Demand charge', cost.demand_charge],
                ['Network', (cost.network_distribution || 0) + (cost.network_transmission || 0) + (cost.network_metering || 0)],
                ['Fixed supply', cost.fixed_supply],
                ['Environmental', cost.environmental],
              ].filter(([_, v]) => v > 0).map(([label, v]) => (
                <tr key={label} className="border-t border-line">
                  <td className="px-3 py-2 text-ink-soft">{label}</td>
                  <td className="px-3 py-2 text-right tabnum text-forest-900">{fmtCurrency(v)}</td>
                </tr>
              ))}
              <tr className="border-t-2 border-forest-200 bg-cream-100">
                <td className="px-3 py-2 font-semibold text-forest-900">Total annual</td>
                <td className="px-3 py-2 text-right tabnum font-bold text-violet">{fmtCurrency(cost.total_annual || 0)}</td>
              </tr>
            </tbody>
          </table>
        </section>

        {/* Scenarios */}
        {scenarios.map((s, i) => (
          <section key={s.id || i}>
            <h2 className="text-[11px] uppercase tracking-widest text-ink-mute mb-3">
              Proposed Plan {i + 1}
            </h2>
            <div className="border border-line rounded-2xl p-5 bg-cream-50">
              <div className="flex items-baseline justify-between mb-3 gap-4">
                <h3 className="font-display text-xl text-forest-900">{s.name}</h3>
                <p className="text-base font-display text-violet tabnum">
                  {fmtCurrency(s.savings_annual_low)}–{fmtCurrency(s.savings_annual_high)} /yr
                </p>
              </div>
              {s.rationale && <p className="text-sm text-ink-soft mb-4">{s.rationale}</p>}

              {/* Load curve */}
              {s.baseline_curve && s.shifted_curve && (
                <div className="mb-4">
                  <p className="text-[10px] uppercase tracking-wider text-ink-mute mb-1">Hourly load — before vs after</p>
                  <StackedAreaChart
                    applianceCurves={s.baseline_appliance_curves || {}}
                    scales={{}}
                    height={180}
                    baseline={s.baseline_curve}
                    overlay={s.shifted_curve}
                    showTooltip={false}
                    testId={`report-scenario-chart-${i}`}
                  />
                </div>
              )}

              {/* Appliance changes summary */}
              {s.appliance_changes && s.appliance_changes.length > 0 && (
                <div className="mb-4">
                  <p className="text-[10px] uppercase tracking-wider text-ink-mute mb-2">Appliance changes</p>
                  <ul className="text-xs space-y-1">
                    {s.appliance_changes.map((c, j) => (
                      <li key={j} className="flex items-start gap-2">
                        <span className="font-semibold text-forest-800 min-w-[80px]">{c.appliance}</span>
                        <span className="text-ink-soft">{c.summary}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Retailer + levers */}
              {(s.retailer_winner || (s.negotiation_levers && s.negotiation_levers.length > 0)) && (
                <div className="bg-violet/5 border border-violet/30 rounded-xl p-3">
                  {s.retailer_winner && (
                    <p className="text-xs mb-2">
                      <span className="text-ink-mute">Recommended retailer: </span>
                      <span className="font-semibold text-violet">{s.retailer_winner}</span>
                    </p>
                  )}
                  {s.negotiation_levers && (
                    <ul className="text-xs space-y-1">
                      {s.negotiation_levers.map((lev, k) => (
                        <li key={k} className="flex items-start gap-2 text-ink-soft">
                          <span className="text-violet font-bold flex-shrink-0">→</span>
                          <span>{lev}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>
          </section>
        ))}

        {/* Total savings */}
        {scenarios.length > 0 && (
          <section>
            <div className="bg-forest-800 text-white rounded-2xl p-6 text-center">
              <p className="text-[10px] uppercase tracking-[0.2em] text-lime mb-2">Total annual saving range</p>
              <p className="font-display text-4xl tabnum">
                {fmtCurrency(totalLow)} <span className="text-lime/60 text-2xl mx-2">–</span> {fmtCurrency(totalHigh)}
              </p>
              <p className="text-xs text-forest-100/60 mt-2">3-year estimate: {fmtCurrency(totalLow * 3)} – {fmtCurrency(totalHigh * 3)}</p>
            </div>
          </section>
        )}
      </div>

      <div className="border-t border-line px-10 py-4 bg-cream-100 flex items-center justify-between text-[11px] text-ink-mute">
        <span>Generated by EnergyScope</span>
        <span>{generatedAt}</span>
      </div>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────
export default function Report() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const focusId = params.get('focus');

  const [client, setClient] = useState(null);
  const [reports, setReports] = useState([]);
  const [activeReport, setActiveReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState('');

  const docRef = useRef(null);

  useEffect(() => {
    const fetch = async () => {
      try {
        const [clientRes, reportsRes] = await Promise.all([getClient(id), listReports(id)]);
        setClient(clientRes.data);
        sessionStorage.setItem(`client_name_${id}`, clientRes.data.name);
        const list = reportsRes.data || [];
        setReports(list);
        if (focusId) {
          const matched = list.find((r) => r.id === focusId);
          if (matched) setActiveReport(matched);
        }
      } catch (err) {
        setError(err.response?.data?.detail || 'Failed to load reports.');
      } finally {
        setLoading(false);
      }
    };
    fetch();
  }, [id, focusId]);

  const openReport = async (rid) => {
    try {
      const res = await getReport(rid);
      setActiveReport(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to open report.');
    }
  };

  const handleDelete = async (rid) => {
    if (!window.confirm('Delete this report?')) return;
    await deleteReport(rid);
    setReports((cur) => cur.filter((r) => r.id !== rid));
    if (activeReport?.id === rid) setActiveReport(null);
  };

  const handleExport = async () => {
    if (!docRef.current || !activeReport) return;
    setExporting(true);
    try {
      const safe = (activeReport.title || 'report').replace(/[^a-z0-9-_]+/gi, '-').toLowerCase();
      await exportPdf(docRef.current, `${safe}.pdf`);
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="p-10 max-w-7xl" data-testid="reports-page">
      <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.15em] text-ink-mute mb-3 no-print">
        <Link to="/clients" className="hover:text-forest-700">Clients</Link>
        <ChevronRight size={12} />
        {client && (
          <Link to={`/clients/${id}/baseline`} className="hover:text-forest-700 text-forest-800 font-medium">
            {client.name}
          </Link>
        )}
        <ChevronRight size={12} />
        <span className="text-violet font-medium">Reports</span>
      </div>

      <div className="flex items-end justify-between mb-8 gap-6 no-print">
        <div>
          <h1 className="font-display text-5xl text-forest-900 leading-none">Reports.</h1>
          <p className="text-sm text-ink-soft mt-3 max-w-xl">
            Saved snapshots you can share with clients. Pick scenarios on the Scenarios page, then click <em>Create report</em>.
          </p>
        </div>
        {activeReport && (
          <button
            type="button"
            onClick={handleExport}
            disabled={exporting}
            data-testid="download-pdf-btn"
            className="btn-violet inline-flex items-center gap-2 font-semibold rounded-full px-5 py-2.5 text-sm transition-all disabled:opacity-50"
          >
            {exporting ? <Loader size={14} className="animate-spin" /> : <Download size={14} />}
            {exporting ? 'Building PDF…' : 'Download PDF'}
          </button>
        )}
      </div>

      {error && (
        <div className="flex items-start gap-2 bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm mb-6 no-print">
          <AlertCircle size={16} className="mt-0.5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader size={22} className="animate-spin text-violet" />
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-7 gap-6">
          {/* Left rail — reports list */}
          <aside className="lg:col-span-2 space-y-3 no-print">
            <h2 className="text-[11px] uppercase tracking-wider text-ink-mute">Saved reports</h2>
            {reports.length === 0 ? (
              <div className="border-2 border-dashed border-line rounded-2xl p-6 text-center bg-cream-50">
                <FileText size={20} className="mx-auto text-ink-mute mb-2" />
                <p className="text-xs text-ink-soft mb-3">No reports yet.</p>
                <Link
                  to={`/clients/${id}/scenarios`}
                  data-testid="goto-scenarios-link"
                  className="inline-flex items-center gap-1 text-xs text-violet hover:text-violet-700 font-semibold"
                >
                  <Plus size={12} /> Create one from Scenarios
                </Link>
              </div>
            ) : (
              <div className="space-y-2" data-testid="reports-list">
                {reports.map((r) => (
                  <div
                    key={r.id}
                    data-testid={`report-item-${r.id}`}
                    className={`border rounded-xl p-3 cursor-pointer transition-all ${
                      activeReport?.id === r.id ? 'border-violet bg-violet/5 ring-2 ring-violet/20' : 'border-line bg-cream-50 hover:border-forest-300'
                    }`}
                    onClick={() => openReport(r.id)}
                  >
                    <p className="font-semibold text-sm text-forest-900 truncate">{r.title}</p>
                    <p className="text-[11px] text-ink-mute mt-1 flex items-center gap-1">
                      <Calendar size={10} />
                      {new Date(r.created_at).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })}
                    </p>
                    <p className="text-[11px] text-ink-mute">{(r.scenarios || []).length} scenario{(r.scenarios || []).length === 1 ? '' : 's'}</p>
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); handleDelete(r.id); }}
                      className="mt-2 text-[11px] inline-flex items-center gap-1 text-ink-mute hover:text-red-600"
                    >
                      <Trash2 size={11} /> Delete
                    </button>
                  </div>
                ))}
              </div>
            )}
          </aside>

          {/* Right — active report */}
          <div className="lg:col-span-5">
            {activeReport ? (
              <ReportDocument report={activeReport} innerRef={docRef} />
            ) : (
              <div className="border-2 border-dashed border-line rounded-3xl p-16 text-center bg-cream-50">
                <FileText size={32} className="mx-auto text-ink-mute mb-3" />
                <h3 className="font-display text-2xl text-forest-900 mb-1">
                  {reports.length === 0 ? 'Nothing to report — yet.' : 'Select a report'}
                </h3>
                <p className="text-sm text-ink-mute max-w-md mx-auto">
                  {reports.length === 0
                    ? 'Generate scenarios first, then bundle them into a report from the Scenarios page.'
                    : 'Pick one from the left to preview it here. The PDF export button will appear in the header.'}
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
