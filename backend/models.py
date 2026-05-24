"""Pydantic models for the energy broker API."""
from __future__ import annotations

from typing import Dict, List, Optional
from pydantic import BaseModel


# ── Auth ────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str


class Broker(BaseModel):
    id: str
    name: str
    email: str
    firm: str


class TokenResponse(BaseModel):
    token: str
    broker: Broker


# ── Clients ─────────────────────────────────────────────────────────────────

class ClientCreate(BaseModel):
    name: str
    address: str
    nmi: Optional[str] = None
    site_type: str = "office"


class Client(BaseModel):
    id: str
    broker_id: str
    name: str
    address: str
    nmi: Optional[str] = None
    site_type: str
    status: str
    created_at: str
    has_interval_data: bool
    has_tariff: bool
    tariff_id: Optional[str] = None
    annual_kwh: Optional[float] = None
    annual_cost: Optional[float] = None


# ── Intervals ───────────────────────────────────────────────────────────────

class IntervalRecord(BaseModel):
    timestamp: str
    kwh: float  # kWh per 30-min interval


class UploadResponse(BaseModel):
    success: bool
    intervals_count: int
    date_range: Dict[str, str]
    annual_kwh: float
    peak_kw: float


class IntervalSummary(BaseModel):
    date_range: Dict[str, str]
    annual_kwh: float
    peak_kw: float
    load_factor: float
    typical_weekday: List[float]  # 48 half-hourly kW values


# ── Tariffs ─────────────────────────────────────────────────────────────────

class TariffRate(BaseModel):
    peak: Optional[float] = None
    shoulder: Optional[float] = None
    offpeak: Optional[float] = None
    flat: Optional[float] = None


class NetworkCharges(BaseModel):
    distribution: float = 0.0
    transmission: float = 0.0
    metering: float = 0.0
    service: float = 0.0


class Tariff(BaseModel):
    id: str
    retailer: str
    plan_name: str
    type: str   # "TOU" | "Flat" | "Demand"
    state: str
    supply_charge: float          # $/day (excl GST)
    energy_rates: TariffRate
    demand_charge: Optional[float] = None   # $/kW/month
    network_charges: NetworkCharges
    environmental_levy: float = 0.0


class TariffAssign(BaseModel):
    tariff_id: str


# ── Baseline ────────────────────────────────────────────────────────────────

class CostStack(BaseModel):
    energy_peak: float
    energy_shoulder: float
    energy_offpeak: float
    demand_charge: float
    network_distribution: float
    network_transmission: float
    network_metering: float
    fixed_supply: float
    environmental: float
    total_annual: float


class ShapeMetrics(BaseModel):
    load_factor: float
    peak_kw: float
    peak_coincidence: float
    annual_kwh: float
    avg_daily_kwh: float
    max_demand_month: str


class BaselineResponse(BaseModel):
    load_curve: List[float]
    cost_stack: CostStack
    shape_metrics: ShapeMetrics


# ── Scenarios ───────────────────────────────────────────────────────────────

class ScenarioRun(BaseModel):
    type: str
    parameters: dict


class ScenarioRunRequest(BaseModel):
    scenarios: List[ScenarioRun]


class BillingDefensibleSavings(BaseModel):
    energy: float
    demand: float
    total: float


class IndicativeSavings(BaseModel):
    contract_low: float
    contract_high: float


class SavingsSummary(BaseModel):
    billing_defensible: BillingDefensibleSavings
    indicative: IndicativeSavings
    total_low: float
    total_high: float


class ScenarioResult(BaseModel):
    baseline_curve: List[float]
    shifted_curve: List[float]
    scenarios_applied: List[dict]
    savings: SavingsSummary
    new_shape_metrics: ShapeMetrics


# ── Report ───────────────────────────────────────────────────────────────────

class ReportResponse(BaseModel):
    client: dict
    baseline: Optional[dict] = None
    scenarios: Optional[List[dict]] = None
    savings: Optional[dict] = None
    generated_at: str
