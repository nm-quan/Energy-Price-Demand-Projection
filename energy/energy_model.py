import pulp
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

# ==========================================
# MODULE 1: Data Definition
# ==========================================
def run_dispatch(demand):
    """
    Convenience entry point: given a 24-hour demand dict (or list), build,
    solve, and return (results_df, total_cost, status_str).
    Uses the VIC1-scale fleet parameters.
    """
    if not isinstance(demand, dict):
        demand = {i: float(v) for i, v in enumerate(list(demand)[:24])}

    T, dt, _, thermal, battery, hydro = load_parameters(demand_csv=None)
    # Override with VIC1-scale fleet (same as the demand_csv branch)
    thermal = {
        'Coal':       {'C': 30,  'P_min': 1500, 'P_max': 5000, 'R_up': 400,  'R_down': 400},
        'Gas_Steam':  {'C': 80,  'P_min': 200,  'P_max': 2000, 'R_up': 500,  'R_down': 500},
        'Gas_Peaker': {'C': 150, 'P_min': 0,    'P_max': 1500, 'R_up': 1200, 'R_down': 1200},
    }
    battery = {'C_batt': 5, 'E_max': 800, 'E_0': 400, 'P_max': 300,
               'eta_c': 0.95, 'eta_d': 0.95}
    hydro = {'C_hydro': 2, 'E_max': 2000, 'E_0': 1000,
             'P_pump_max': 500, 'P_gen_max': 600,
             'eta_pump': 0.85, 'eta_gen': 0.90}

    vars = initialize_variables(T, thermal)
    prob = build_model(T, dt, demand, thermal, battery, hydro, vars)
    prob.solve(pulp.PULP_CBC_CMD(msg=0))
    status = pulp.LpStatus[prob.status]
    cost = pulp.value(prob.objective) if status == 'Optimal' else None

    if status != 'Optimal':
        return None, cost, status

    P, P_batt_ch, P_batt_dis, E_batt, P_hydro_pump, P_hydro_gen, E_hydro = vars
    rows = []
    for t in range(T):
        rows.append({
            'Time': t,
            'Demand_MW': demand[t],
            'Coal_MW': P['Coal', t].varValue,
            'Gas_Steam_MW': P['Gas_Steam', t].varValue,
            'Gas_Peaker_MW': P['Gas_Peaker', t].varValue,
            'Batt_Discharge_MW': P_batt_dis[t].varValue,
            'Batt_Charge_MW': -P_batt_ch[t].varValue,
            'Batt_SoC_MWh': E_batt[t].varValue,
            'Hydro_Gen_MW': P_hydro_gen[t].varValue,
            'Hydro_Pump_MW': -P_hydro_pump[t].varValue,
            'Hydro_Res_MWh': E_hydro[t].varValue,
        })
    return pd.DataFrame(rows).set_index('Time'), cost, status


def load_demand_from_csv(csv_path, demand_col='TOTALDEMAND', time_col='SETTLEMENTDATE'):
    """
    Read a sub-hourly demand CSV (5-min AEMO style) and resample to hourly mean.
    Returns dict {hour: MW} for 24 hours.
    """
    df = pd.read_csv(csv_path, parse_dates=[time_col])
    df = df.set_index(time_col).sort_index()
    hourly = df[demand_col].resample('1h').mean()
    return {i: float(v) for i, v in enumerate(hourly.values[:24])}


def load_parameters(demand_csv=None):
    """
    Loads system, thermal, battery, and hydro parameters.
    If demand_csv is provided, demand is read from that file; otherwise a mock
    sinusoidal profile is used.
    """
    T = 24
    dt = 1.0

    if demand_csv is not None:
        demand = load_demand_from_csv(demand_csv)
        # VIC1-scale fleet (~3.3-5.8 GW load)
        thermal = {
            'Coal':       {'C': 30,  'P_min': 1500, 'P_max': 4200, 'R_up': 300, 'R_down': 300},
            'Gas_Steam':  {'C': 80,  'P_min': 200,  'P_max': 1500, 'R_up': 400, 'R_down': 400},
            'Gas_Peaker': {'C': 150, 'P_min': 0,    'P_max': 1000, 'R_up': 800, 'R_down': 800},
        }
        battery = {
            'C_batt': 5,
            'E_max': 800, 'E_0': 400,
            'P_max': 300,
            'eta_c': 0.95, 'eta_d': 0.95,
        }
        hydro = {
            'C_hydro': 2,
            'E_max': 2000, 'E_0': 1000,
            'P_pump_max': 500, 'P_gen_max': 600,
            'eta_pump': 0.85, 'eta_gen': 0.90,
        }
    else:
        import math
        demand = {t: int(1200 + 600 * math.sin(math.pi * (t - 6) / 12)) for t in range(T)}
        thermal = {
            'Coal':       {'C': 30,  'P_min': 400, 'P_max': 1200, 'R_up': 150, 'R_down': 150},
            'Gas_Steam':  {'C': 80,  'P_min': 100, 'P_max': 600,  'R_up': 200, 'R_down': 200},
            'Gas_Peaker': {'C': 120, 'P_min': 0,   'P_max': 300,  'R_up': 300, 'R_down': 300},
        }
        battery = {
            'C_batt': 5, 'E_max': 200, 'E_0': 100, 'P_max': 50,
            'eta_c': 0.95, 'eta_d': 0.95,
        }
        hydro = {
            'C_hydro': 2, 'E_max': 1000, 'E_0': 500,
            'P_pump_max': 200, 'P_gen_max': 250,
            'eta_pump': 0.85, 'eta_gen': 0.90,
        }

    return T, dt, demand, thermal, battery, hydro

# ==========================================
# MODULE 2: Variable Initialization
# ==========================================
def initialize_variables(T, thermal):
    """
    Creates PuLP decision variables for the optimization problem.
    """
    time_steps = range(T)
    generators = list(thermal.keys())
    
    # Thermal variables
    P = pulp.LpVariable.dicts("P", ((i, t) for i in generators for t in time_steps), lowBound=0)
    
    # Battery variables
    P_batt_ch = pulp.LpVariable.dicts("P_batt_ch", time_steps, lowBound=0)
    P_batt_dis = pulp.LpVariable.dicts("P_batt_dis", time_steps, lowBound=0)
    E_batt = pulp.LpVariable.dicts("E_batt", time_steps, lowBound=0)
    
    # Hydro variables
    P_hydro_pump = pulp.LpVariable.dicts("P_hydro_pump", time_steps, lowBound=0)
    P_hydro_gen = pulp.LpVariable.dicts("P_hydro_gen", time_steps, lowBound=0)
    E_hydro = pulp.LpVariable.dicts("E_hydro", time_steps, lowBound=0)
    
    return P, P_batt_ch, P_batt_dis, E_batt, P_hydro_pump, P_hydro_gen, E_hydro

# ==========================================
# MODULE 3: Model Construction
# ==========================================
def build_model(T, dt, demand, thermal, battery, hydro, vars):
    """
    Builds the objective function and constraints.
    """
    prob = pulp.LpProblem("Economic_Dispatch_With_Storage", pulp.LpMinimize)
    
    # Unpack variables
    P, P_batt_ch, P_batt_dis, E_batt, P_hydro_pump, P_hydro_gen, E_hydro = vars
    time_steps = range(T)
    generators = list(thermal.keys())

    # --- OBJECTIVE FUNCTION ---
    # Minimize: Thermal Costs + Battery Degradation Cost + Hydro Cycling Cost
    prob += pulp.lpSum(
        thermal[i]['C'] * P[i, t] * dt for i in generators for t in time_steps
    ) + pulp.lpSum(
        battery['C_batt'] * (P_batt_ch[t] + P_batt_dis[t]) * dt for t in time_steps
    ) + pulp.lpSum(
        hydro['C_hydro'] * (P_hydro_pump[t] + P_hydro_gen[t]) * dt for t in time_steps
    )

    # --- CONSTRAINTS ---
    for t in time_steps:
        # 1. Power Balance
        prob += (
            pulp.lpSum(P[i, t] for i in generators) 
            + P_batt_dis[t] - P_batt_ch[t] 
            + P_hydro_gen[t] - P_hydro_pump[t] 
            == demand[t], 
            f"Power_Balance_{t}"
        )
        
        # 2. Thermal Limits & Ramping
        for i in generators:
            # Capacity limits
            prob += P[i, t] >= thermal[i]['P_min'], f"Min_Gen_{i}_{t}"
            prob += P[i, t] <= thermal[i]['P_max'], f"Max_Gen_{i}_{t}"
            
            # Ramping limits (skip t=0 since we don't have t-1 data in this mock)
            if t > 0:
                prob += P[i, t] - P[i, t-1] <= thermal[i]['R_up'], f"Ramp_Up_{i}_{t}"
                prob += P[i, t-1] - P[i, t] <= thermal[i]['R_down'], f"Ramp_Down_{i}_{t}"
                
        # 3. Battery Limits & Energy Balance
        prob += P_batt_ch[t] <= battery['P_max'], f"Batt_Max_Charge_{t}"
        prob += P_batt_dis[t] <= battery['P_max'], f"Batt_Max_Discharge_{t}"
        prob += E_batt[t] <= battery['E_max'], f"Batt_Max_Energy_{t}"
        
        if t == 0:
            prob += E_batt[t] == battery['E_0'] + (P_batt_ch[t] * battery['eta_c'] * dt) - ((P_batt_dis[t] / battery['eta_d']) * dt)
        else:
            prob += E_batt[t] == E_batt[t-1] + (P_batt_ch[t] * battery['eta_c'] * dt) - ((P_batt_dis[t] / battery['eta_d']) * dt)

        # 4. Hydro Limits & Reservoir Balance
        prob += P_hydro_pump[t] <= hydro['P_pump_max'], f"Hydro_Max_Pump_{t}"
        prob += P_hydro_gen[t] <= hydro['P_gen_max'], f"Hydro_Max_Gen_{t}"
        prob += E_hydro[t] <= hydro['E_max'], f"Hydro_Max_Energy_{t}"
        
        if t == 0:
            prob += E_hydro[t] == hydro['E_0'] + (P_hydro_pump[t] * hydro['eta_pump'] * dt) - ((P_hydro_gen[t] / hydro['eta_gen']) * dt)
        else:
            prob += E_hydro[t] == E_hydro[t-1] + (P_hydro_pump[t] * hydro['eta_pump'] * dt) - ((P_hydro_gen[t] / hydro['eta_gen']) * dt)

    return prob

# ==========================================
# MODULE 4: Execution and Reporting
# ==========================================
def solve_and_report(prob, T, vars, demand):
    """
    Solves the problem and extracts variables into a Pandas DataFrame.
    """
    # Solve the model
    prob.solve()
    print(f"Status: {pulp.LpStatus[prob.status]}")
    print(f"Total Objective Cost: ${pulp.value(prob.objective):,.2f}\n")
    
    if pulp.LpStatus[prob.status] != 'Optimal':
        print("Warning: Optimal solution not found.")
        return None

    # Unpack variables
    P, P_batt_ch, P_batt_dis, E_batt, P_hydro_pump, P_hydro_gen, E_hydro = vars
    
    # Extract results into a list of dictionaries for Pandas
    results = []
    for t in range(T):
        row = {
            'Time': t,
            'Demand_MW': demand[t],
            'Coal_MW': P['Coal', t].varValue,
            'Gas_Steam_MW': P['Gas_Steam', t].varValue,
            'Gas_Peaker_MW': P['Gas_Peaker', t].varValue,
            'Batt_Discharge_MW': P_batt_dis[t].varValue,
            'Batt_Charge_MW': -P_batt_ch[t].varValue,  # Negative for visual clarity
            'Batt_SoC_MWh': E_batt[t].varValue,
            'Hydro_Gen_MW': P_hydro_gen[t].varValue,
            'Hydro_Pump_MW': -P_hydro_pump[t].varValue, # Negative for visual clarity
            'Hydro_Res_MWh': E_hydro[t].varValue
        }
        results.append(row)
        
    df = pd.DataFrame(results).set_index('Time')
    return df

# ==========================================
# MODULE 5: Plotting
# ==========================================
def plot_generation_stack(df):
    """
    Stacked-area generation mix vs demand line (sample.png style).
    Positive stack: dispatched generation (thermal + storage discharge).
    Negative stack: load-absorbing storage (battery charging, hydro pumping).
    Demand is overlaid as a clear line on top of the positive stack.
    """
    hours = df.index

    pos_sources = {
        'Coal':        ('#2b2b2b', df['Coal_MW']),
        'Gas Steam':   ('#5a8fbf', df['Gas_Steam_MW']),
        'Gas Peaker':  ('#f5b04a', df['Gas_Peaker_MW']),
        'Hydro Gen':   ('#3aa66d', df['Hydro_Gen_MW']),
        'Battery Dis': ('#7e57c2', df['Batt_Discharge_MW']),
    }
    neg_sources = {
        'Hydro Pump':  ('#8d6e63', -df['Hydro_Pump_MW']),   # stored as negative already; flip back
        'Battery Chg': ('#b39ddb', -df['Batt_Charge_MW']),
    }

    fig, ax = plt.subplots(figsize=(12, 6))

    ax.stackplot(hours,
                 [v for _, v in pos_sources.values()],
                 labels=list(pos_sources.keys()),
                 colors=[c for c, _ in pos_sources.values()],
                 alpha=0.9)

    ax.stackplot(hours,
                 [-v for _, v in neg_sources.values()],
                 labels=list(neg_sources.keys()),
                 colors=[c for c, _ in neg_sources.values()],
                 alpha=0.7)

    ax.plot(hours, df['Demand_MW'], color='red', linewidth=2.5,
            marker='o', markersize=4, label='Demand', zorder=5)

    ax.axhline(0, color='black', linewidth=0.8)
    ax.set_xlabel('Hour')
    ax.set_ylabel('Power (MW)')
    ax.set_title('Generation Mix vs Demand')
    ax.set_xticks(hours)
    ax.grid(True, alpha=0.3, linestyle='--')
    ax.legend(loc='upper left', ncol=2, framealpha=0.9)
    fig.tight_layout()
    plt.show()
    return fig

# ==========================================
# MAIN EXECUTION SCRIPT
# ==========================================
if __name__ == "__main__":
    # 1. Load Data — point at the VIC1 summer-weekend average profile
    demand_csv = Path(__file__).resolve().parent.parent / 'data' / 'processed' / 'average' / 'vic1_2025_summer_weekend.csv'
    T, dt, demand, thermal, battery, hydro = load_parameters(demand_csv=demand_csv)
    
    # 2. Init Variables
    vars = initialize_variables(T, thermal)
    
    # 3. Build Model
    prob = build_model(T, dt, demand, thermal, battery, hydro, vars)
    
    # 4. Solve and format output
    results_df = solve_and_report(prob, T, vars, demand)
    
    # Print the first 5 hours of the dispatch schedule
    if results_df is not None:
        print(results_df.head())
        plot_generation_stack(results_df)