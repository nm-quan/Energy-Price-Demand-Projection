import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';

const api = axios.create({
  baseURL: BACKEND_URL,
  timeout: 120000,
});

export const getClients = () => api.get('/api/clients');
export const createClient = (data) => api.post('/api/clients', data);
export const getClient = (id) => api.get(`/api/clients/${id}`);

export const uploadIntervalData = (id, file) => {
  const fd = new FormData();
  fd.append('file', file);
  return api.post(`/api/clients/${id}/upload`, fd);
};
export const getIntervalSummary = (id) => api.get(`/api/clients/${id}/intervals/summary`);

export const getTariffs = () => api.get('/api/tariffs');
export const createTariff = (data) => api.post('/api/tariffs', data);
export const setClientTariff = (id, tariffId) => api.put(`/api/clients/${id}/tariff`, { tariff_id: tariffId });

export const getBaseline = (id) => api.get(`/api/clients/${id}/baseline`);

export const getScenarioLibrary = () => api.get('/api/scenarios/library');
export const runScenarios = (id, scenarios) => api.post(`/api/clients/${id}/scenarios/run`, { scenarios });
export const generateScenarios = (id, extraInstruction = null) =>
  api.post(`/api/clients/${id}/scenarios/generate`, { extra_instruction: extraInstruction });

export const getReport = (id) => api.get(`/api/clients/${id}/report`);

// Formatters
export const fmtCurrency = (n) =>
  new Intl.NumberFormat('en-AU', {
    style: 'currency',
    currency: 'AUD',
    maximumFractionDigits: 0,
  }).format(n ?? 0);

export const fmtNumber = (n, digits = 1) =>
  new Intl.NumberFormat('en-AU', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(n ?? 0);

export const fmtPct = (n, digits = 0) =>
  new Intl.NumberFormat('en-AU', {
    style: 'percent',
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(n ?? 0);

export const bucketToTime = (b) => {
  const h = Math.floor(b / 2);
  const m = (b % 2) * 30;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
};

export default api;
