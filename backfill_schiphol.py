import os
import requests
import pandas as pd
import numpy as np

LAT = "52.3081"
LON = "4.7642"

# Het historische archief-endpoint voor ECMWF IFS runs
HIST_URL = (
    f"https://historical-forecast-api.open-meteo.com/v1/forecast?"
    f"latitude={LAT}&longitude={LON}&"
    f"start_date=2026-09-23&end_date=2026-09-24&"
    f"hourly=temperature_2m,wind_speed_10m,wind_direction_10m,wind_gusts_10m&"
    f"models=ecmwf_ifs025&wind_speed_unit=kn"
)

# 1. Data ophalen
res = requests.get(HIST_URL, timeout=30)
res.raise_for_status()
hourly = res.json()["hourly"]
df_h = pd.DataFrame(hourly)
df_h['time'] = pd.to_datetime(df_h['time'])
df_h['forecast_date'] = df_h['time'].dt.strftime('%Y-%m-%d')
df_h['hour'] = df_h['time'].dt.hour

# 2. Dagdelen filteren
df_m = df_h[(df_h['hour'] >= 6) & (df_h['hour'] < 12)]
df_a = df_h[(df_h['hour'] >= 12) & (df_h['hour'] < 18)]
df_e = df_h[(df_h['hour'] >= 18) & (df_h['hour'] < 24)]

# Leden detecteren (of single model fallback indien al geaggregeerd)
temp_cols = [c for c in df_h.columns if c.startswith("temperature_2m")]
ws_cols   = [c for c in df_h.columns if c.startswith("wind_speed_10m")]
wd_cols   = [c for c in df_h.columns if c.startswith("wind_direction_10m")]
wg_cols   = [c for c in df_h.columns if c.startswith("wind_gusts_10m")]

def calc_lin(df_slice, cols, stat_func):
    matrix = df_slice[cols].values
    if stat_func == 'mean':
        return np.nanmean(matrix)
    elif stat_func == 'min':
        return np.nanmin(matrix)
    elif stat_func == 'max':
        return np.nanmax(matrix)
    elif stat_func == 'var':
        return np.nanvar(matrix)

def calc_circ(df_slice, cols):
    matrix = df_slice[cols].values
    rad = np.deg2rad(matrix)
    X = np.nanmean(np.cos(rad))
    Y = np.nanmean(np.sin(rad))
    mean_deg = (np.rad2deg(np.arctan2(Y, X)) + 360) % 360
    R = np.sqrt(X**2 + Y**2)
    var = 1.0 - R
    std_deg = np.minimum(np.rad2deg(np.sqrt(-2 * np.log(np.clip(R, 1e-6, 1.0)))), 180.0)
    return (mean_deg - std_deg) % 360, (mean_deg + std_deg) % 360, mean_deg, var

# De 3 doelsleutels die NaN zijn
missing_keys = [
    ("2026-09-22", "2026-09-23"),
    ("2026-09-22", "2026-09-24"),
    ("2026-09-23", "2026-09-24")
]

# Bereken de stats per datum (2026-09-23 en 2026-09-24)
dates_data = {}
for f_date in ["2026-09-23", "2026-09-24"]:
    sub_m = df_m[df_m['forecast_date'] == f_date]
    sub_a = df_a[df_a['forecast_date'] == f_date]
    sub_e = df_e[df_e['forecast_date'] == f_date]
    sub_all = df_h[df_h['forecast_date'] == f_date]

    # Temp
    t_vals = {}
    for part_name, sub in [('morning_mean', sub_m), ('afternoon_mean', sub_a), ('evening_mean', sub_e)]:
        t_vals[f'{part_name}_low'] = calc_lin(sub, temp_cols, 'min')
        t_vals[f'{part_name}_high'] = calc_lin(sub, temp_cols, 'max')
        t_vals[f'{part_name}_mean'] = calc_lin(sub, temp_cols, 'mean')
        t_vals[f'{part_name}_var'] = calc_lin(sub, temp_cols, 'var')
    t_vals['daily_max_low'] = calc_lin(sub_all, temp_cols, 'min')
    t_vals['daily_max_high'] = calc_lin(sub_all, temp_cols, 'max')
    t_vals['daily_max_mean'] = calc_lin(sub_all, temp_cols, 'mean')
    t_vals['daily_max_var'] = calc_lin(sub_all, temp_cols, 'var')

    # Wind speed & gusts
    w_vals = {}
    for part_name, sub in [('morning_max', sub_m), ('afternoon_max', sub_a), ('evening_max', sub_e)]:
        w_vals[f'{part_name}_low'] = calc_lin(sub, ws_cols, 'min')
        w_vals[f'{part_name}_high'] = calc_lin(sub, ws_cols, 'max')
        w_vals[f'{part_name}_mean'] = calc_lin(sub, ws_cols, 'mean')
        w_vals[f'{part_name}_var'] = calc_lin(sub, ws_cols, 'var')
    if wg_cols:
        w_vals['morning_gust_mean'] = calc_lin(sub_m, wg_cols, 'mean')
        w_vals['afternoon_gust_mean'] = calc_lin(sub_a, wg_cols, 'mean')
        w_vals['evening_gust_mean'] = calc_lin(sub_e, wg_cols, 'mean')

    # Wind dir
    d_vals = {}
    for part_name, sub in [('morning_dir', sub_m), ('afternoon_dir', sub_a), ('evening_dir', sub_e)]:
        low, high, mean, var = calc_circ(sub, wd_cols)
        d_vals[f'{part_name}_low'] = low
        d_vals[f'{part_name}_high'] = high
        d_vals[f'{part_name}_mean'] = mean
        d_vals[f'{part_name}_var'] = var

    dates_data[f_date] = {'temp': t_vals, 'wind': w_vals, 'dir': d_vals}

# Functie om direct in de master CSV te patchen
def patch_file(filename, category):
    if not os.path.exists(filename):
        return
    df = pd.read_csv(filename, keep_default_na=True, na_values=['', ' ', 'nan', 'NaN'])
    for init_d, f_d in missing_keys:
        mask = (df['init_date'] == init_d) & (df['forecast_date'] == f_d)
        if mask.any() and f_d in dates_data:
            vals = dates_data[f_d][category]
            for col, val in vals.items():
                if col in df.columns:
                    df.loc[mask, col] = val
    df.to_csv(filename, index=False)
    print(f"Gepatched: {filename}")

patch_file("schiphol_temperature_archive.csv", "temp")
patch_file("schiphol_wind_speed_archive.csv", "wind")
patch_file("schiphol_wind_direction_archive.csv", "dir")

# Verificatie
check = pd.read_csv("schiphol_temperature_archive.csv")
sub = check[check['init_date'].isin(["2026-09-22", "2026-09-23"])]
print("\n--- RESULTAAT NA PATCH ---")
print(sub[['init_date', 'forecast_date', 'lead_time_days', 'morning_mean_mean']].to_string(index=False))
