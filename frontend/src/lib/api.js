import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

export const api = axios.create({
  baseURL: API,
  timeout: 15000,
});

export const fmtCurrency = (n) =>
  new Intl.NumberFormat("en-AU", {
    style: "currency",
    currency: "AUD",
    maximumFractionDigits: 0,
  }).format(n ?? 0);

export const fmtNumber = (n, digits = 1) =>
  new Intl.NumberFormat("en-AU", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(n ?? 0);

export const fmtPct = (n, digits = 0) =>
  new Intl.NumberFormat("en-AU", {
    style: "percent",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(n ?? 0);

export const bucketToTime = (b) => {
  const h = Math.floor(b / 2);
  const m = (b % 2) * 30;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
};
