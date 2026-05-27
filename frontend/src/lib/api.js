import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';

const api = axios.create({
  baseURL: BACKEND_URL,
  timeout: 180000,
});

// Clients
export const getClients = () => api.get('/api/clients');
export const createClient = (data) => api.post('/api/clients', data);
export const getClient = (id) => api.get(`/api/clients/${id}`);
export const deleteClient = (id) => api.delete(`/api/clients/${id}`);

// Stores
export const listStores = (clientId) => api.get(`/api/clients/${clientId}/stores`);
export const createStore = (clientId, data) => api.post(`/api/clients/${clientId}/stores`, data);
export const deleteStore = (clientId, storeId) => api.delete(`/api/clients/${clientId}/stores/${storeId}`);
export const getStoreBaseline = (clientId, storeId) => api.get(`/api/clients/${clientId}/stores/${storeId}/baseline`);
export const getAggregateBaseline = (clientId, storeIds) =>
  api.post(`/api/clients/${clientId}/stores/aggregate-baseline`, { store_ids: storeIds });

// Intervals
export const uploadIntervalData = (id, file) => {
  const fd = new FormData();
  fd.append('file', file);
  return api.post(`/api/clients/${id}/upload`, fd);
};
export const getIntervalSummary = (id) => api.get(`/api/clients/${id}/intervals/summary`);

// Tariffs
export const getTariffs = () => api.get('/api/tariffs');
export const createTariff = (data) => api.post('/api/tariffs', data);
export const setClientTariff = (id, tariffId) => api.put(`/api/clients/${id}/tariff`, { tariff_id: tariffId });

// Baseline
export const getBaseline = (id) => api.get(`/api/clients/${id}/baseline`);
export const recalcBaseline = (id, scales) => api.post(`/api/clients/${id}/baseline/recalc`, { scales });

// Scenarios
export const startGenerateScenarios = (id, count, extraInstruction = null, aggregateStoreIds = null, targetAppliance = null) =>
  api.post(`/api/clients/${id}/scenarios/generate`, {
    count,
    extra_instruction: extraInstruction,
    aggregate_store_ids: aggregateStoreIds,
    target_appliance: targetAppliance,
  });
export const getGenerationJob = (jobId) => api.get(`/api/scenarios/jobs/${jobId}`);
export const listScenarios = (id) => api.get(`/api/clients/${id}/scenarios`);
export const deleteScenario = (sid) => api.delete(`/api/scenarios/${sid}`);
export const clearClientScenarios = (id) => api.delete(`/api/clients/${id}/scenarios`);

// Chat
export const chatWithClient = (id, messages, userMessage) =>
  api.post(`/api/clients/${id}/chat`, { messages, user_message: userMessage });

// Reports
export const createReport = (id, payload) => api.post(`/api/clients/${id}/reports`, payload);
export const listReports = (id) => api.get(`/api/clients/${id}/reports`);
export const getReport = (rid) => api.get(`/api/reports/${rid}`);
export const deleteReport = (rid) => api.delete(`/api/reports/${rid}`);

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
