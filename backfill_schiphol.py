import os
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# =========================================================================
# 1. CONFIGURATIE MET PAST_DAYS VOOR HISTORISCHE ENSEMBLE RUNS
# =========================================================================
LAT = "52.3081"
LON = "4.7642"

# past_days=8 zorgt dat we de data van 21 t/m 28 september terugkrijgen
URL = (
    f"https://ensemble-api.open-meteo.com/v1/ensemble?"
    f"latitude={LAT}&longitude={LON}&"
    f"hourly=temperature_2m,wind_speed_10m,wind_direction_10m,wind_gusts_10m&"
    f"models=ecmwf_ifs025&wind_speed_unit=kn&"
    f"past_days=8&forecast_days=8"
)

# De datums die ontbreken tussen 2026-09-21 en 2026-09-29
MISSING_INIT_DATES = [
    "2026-09-22",
    "2026-09-23",
    "2026-09-24",
    "2026-09-25",
    "2026-09-26",
    "2026-09-27",
    "2026-09-28"
]

# =========================================================================
# 2. EXACTE BEREKENINGSFUNCTIES (ONGOUDEN IDENTIEK AAN JOUW PIPELINE)
# =========================================================================
def process_ensemble_stats(df_members, init_date):
    stats = pd.DataFrame(index=df_members.index)
    stats['low'] = df_members.min(axis=1)
    stats['high'] = df_members.max(axis=1)
    stats['mean'] = df_members.mean(axis=1)
    stats['var'] = df_members.var(axis=1)
    stats = stats.reset_index().rename(columns={'index': 'forecast_date'})
    stats['init_date'] = init_date
    stats['lead_time_days'] = (pd.to_datetime(stats['forecast_date']) - pd.to_datetime(init_date)).dt.days
    return stats[(stats['lead_time_days'] >= 1) & (stats['lead_time_days'] <= 7)]

def process_wind_dir_ensemble_stats(df_members, init_date):
    rad = np.deg2rad(df_members)
    X = np.cos(rad).mean(axis=1)
    Y = np.sin(rad).mean(axis=1)
    
    mean_rad = np.arctan2(Y, X)
    mean_deg = np.rad2deg(mean_rad) % 360
    
    R = np.sqrt(X**2 + Y**2)
    circ_var = 1.0 - R
    
    R_clipped = np.clip(R, 1e-6, 1.0)
    circ_std_rad = np.sqrt(-2 * np.log(R_clipped))
    circ_std_deg = np.minimum(np.rad2deg(circ_std_rad), 180.0)
    
    low_deg = (mean_deg - circ_std_deg) % 360
    high_deg = (mean_deg + circ_std_deg) % 360
    
    stats = pd.DataFrame(index=df_members.index)
    stats['low'] = low_deg
    stats['high'] = high_deg
    stats['mean'] = mean_deg
    stats['var'] = circ_var
    
    stats = stats.reset_index().rename(columns={'index': 'forecast_date'})
    stats['init_date'] = init_date
    stats['lead_time_days'] = (pd.to_datetime(stats['forecast_date']) - pd.to_datetime(init_date)).dt.days
    return stats[(stats['lead_time_days'] >= 1) & (stats['lead_time_days'] <= 7)]

def append_and_sort_csv(new_chunk, filename):
    """Voegt de ontbrekende rijen toe, ontdubbelt en sorteert op init_date en lead_time_days"""
    if not os.path.exists(filename):
        new_chunk.to_csv(filename, index=False)
        print(f"Nieuw aangemaakt: {filename}")
        return

    master_df = pd.read_csv(filename)
    combined = pd.concat([master_df, new_chunk], ignore_index=True)
    # Dedupliceren op combinatie van init_date en forecast_date
    combined = combined.drop_duplicates(subset=['init_date', 'forecast_date'], keep='last')
    combined = combined.sort_values(by=['init_date', 'lead_time_days']).reset_index(drop=True)
    combined.to_csv(filename, index=False)
    print(f"Bijgewerkt en geordend: {filename} (Totaal rijen nu: {len(combined)})")

# =========================================================================
# 3. UITVOEREN VAN DE BACKFILL
# =========================================================================
def run_backfill():
    print("Ophalen historische ensemble runs...")
    res = requests.get(URL)
    raw_hourly = res.json()["hourly"]
    df_hourly = pd.DataFrame(raw_hourly)
    df_hourly['time'] = pd.to_datetime(df_hourly['time'])
    df_hourly['forecast_date'] = df_hourly['time'].dt.strftime('%Y-%m-%d')
    df_hourly['hour'] = df_hourly['time'].dt.hour
    
    suffixes = [c.replace("temperature_2m", "") for c in df_hourly.columns if c.startswith("temperature_2m")]
    
    # Tijdsblokken
    df_morning = df_hourly[(df_hourly['hour'] >= 6) & (df_hourly['hour'] < 12)]
    df_afternoon = df_hourly[(df_hourly['hour'] >= 12) & (df_hourly['hour'] < 18)]
    df_evening = df_hourly[(df_hourly['hour'] >= 18) & (df_hourly['hour'] < 24)]

    # Aggregatie per member
    temp_m_mean, temp_a_mean, temp_e_mean, temp_max = pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    wind_m_max, wind_a_max, wind_e_max = pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    wind_gust_m_max, wind_gust_a_max, wind_gust_e_max = pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    dir_m_avg, dir_a_avg, dir_e_avg = pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    for i, suff in enumerate(suffixes):
        t_col = f"temperature_2m{suff}"
        ws_col = f"wind_speed_10m{suff}"
        wd_col = f"wind_direction_10m{suff}"
        wg_col = f"wind_gusts_10m{suff}"
        m_id = f"m{i}"
        
        if t_col in df_hourly.columns and ws_col in df_hourly.columns and wd_col in df_hourly.columns:
            temp_m_mean[m_id] = df_morning.groupby('forecast_date')[t_col].mean()
            temp_a_mean[m_id] = df_afternoon.groupby('forecast_date')[t_col].mean()
            temp_e_mean[m_id] = df_evening.groupby('forecast_date')[t_col].mean()
            temp_max[m_id] = df_hourly.groupby('forecast_date')[t_col].max()
            
            wind_m_max[m_id] = df_morning.groupby('forecast_date')[ws_col].max()
            wind_a_max[m_id] = df_afternoon.groupby('forecast_date')[ws_col].max()
            wind_e_max[m_id] = df_evening.groupby('forecast_date')[ws_col].max()
            
            if wg_col in df_hourly.columns:
                wind_gust_m_max[m_id] = df_morning.groupby('forecast_date')[wg_col].max()
                wind_gust_a_max[m_id] = df_afternoon.groupby('forecast_date')[wg_col].max()
                wind_gust_e_max[m_id] = df_evening.groupby('forecast_date')[wg_col].max()
            
            for df_p, target_df in [(df_morning, dir_m_avg), (df_afternoon, dir_a_avg), (df_evening, dir_e_avg)]:
                rad = np.deg2rad(df_p[wd_col])
                sin_mean = np.sin(rad).groupby(df_p['forecast_date']).mean()
                cos_mean = np.cos(rad).groupby(df_p['forecast_date']).mean()
                target_df[m_id] = (np.rad2deg(np.arctan2(sin_mean, cos_mean)) % 360)

    # Verzameldataframes voor de ontbrekende week
    all_temp_chunks = []
    all_wind_speed_chunks = []
    all_wind_dir_chunks = []

    for target_init in MISSING_INIT_DATES:
        print(f"Berekenen backfill voor init_date: {target_init}...")
        
        # A. Temperatuur
        t_m = process_ensemble_stats(temp_m_mean, target_init).set_index('forecast_date')
        t_a = process_ensemble_stats(temp_a_mean, target_init).set_index('forecast_date')
        t_e = process_ensemble_stats(temp_e_mean, target_init).set_index('forecast_date')
        t_x = process_ensemble_stats(temp_max, target_init).set_index('forecast_date')
        
        t_final = pd.DataFrame(index=t_m.index)
        t_final['init_date'] = t_m['init_date']
        t_final['lead_time_days'] = t_m['lead_time_days']
        for df_part, p in [(t_m, 'morning_mean'), (t_a, 'afternoon_mean'), (t_e, 'evening_mean'), (t_x, 'daily_max')]:
            for stat in ['low', 'high', 'mean', 'var']:
                t_final[f'{p}_{stat}'] = df_part[stat]
        t_final = t_final.reset_index()
        t_final = t_final[['init_date', 'forecast_date', 'lead_time_days'] + [c for c in t_final.columns if c not in ['init_date', 'forecast_date', 'lead_time_days']]]
        all_temp_chunks.append(t_final)

        # B. Wind Speed
        w_m = process_ensemble_stats(wind_m_max, target_init).set_index('forecast_date')
        w_a = process_ensemble_stats(wind_a_max, target_init).set_index('forecast_date')
        w_e = process_ensemble_stats(wind_e_max, target_init).set_index('forecast_date')
        
        w_final = pd.DataFrame(index=w_m.index)
        w_final['init_date'] = w_m['init_date']
        w_final['lead_time_days'] = w_m['lead_time_days']
        for df_part, p in [(w_m, 'morning_max'), (w_a, 'afternoon_max'), (w_e, 'evening_max')]:
            for stat in ['low', 'high', 'mean', 'var']:
                w_final[f'{p}_{stat}'] = df_part[stat]
                
        if not wind_gust_m_max.empty:
            wg_m = process_ensemble_stats(wind_gust_m_max, target_init).set_index('forecast_date')
            wg_a = process_ensemble_stats(wind_gust_a_max, target_init).set_index('forecast_date')
            wg_e = process_ensemble_stats(wind_gust_e_max, target_init).set_index('forecast_date')
            w_final['morning_gust_mean'] = wg_m['mean']
            w_final['afternoon_gust_mean'] = wg_a['mean']
            w_final['evening_gust_mean'] = wg_e['mean']
                
        w_final = w_final.reset_index()
        w_final = w_final[['init_date', 'forecast_date', 'lead_time_days'] + [c for c in w_final.columns if c not in ['init_date', 'forecast_date', 'lead_time_days']]]
        all_wind_speed_chunks.append(w_final)

        # C. Wind Direction
        d_m = process_wind_dir_ensemble_stats(dir_m_avg, target_init).set_index('forecast_date')
        d_a = process_wind_dir_ensemble_stats(dir_a_avg, target_init).set_index('forecast_date')
        d_e = process_wind_dir_ensemble_stats(dir_e_avg, target_init).set_index('forecast_date')
        
        d_final = pd.DataFrame(index=d_m.index)
        d_final['init_date'] = d_m['init_date']
        d_final['lead_time_days'] = d_m['lead_time_days']
        for df_part, p in [(d_m, 'morning_dir'), (d_a, 'afternoon_dir'), (d_e, 'evening_dir')]:
            for stat in ['low', 'high', 'mean', 'var']:
                d_final[f'{p}_{stat}'] = df_part[stat]
                
        d_final = d_final.reset_index()
        d_final = d_final[['init_date', 'forecast_date', 'lead_time_days'] + [c for c in d_final.columns if c not in ['init_date', 'forecast_date', 'lead_time_days']]]
        all_wind_dir_chunks.append(d_final)

    # Invoegen en wegschrijven naar de CSV's
    append_and_sort_csv(pd.concat(all_temp_chunks, ignore_index=True), 'schiphol_temperature_archive.csv')
    append_and_sort_csv(pd.concat(all_wind_speed_chunks, ignore_index=True), 'schiphol_wind_speed_archive.csv')
    append_and_sort_csv(pd.concat(all_wind_dir_chunks, ignore_index=True), 'schiphol_wind_direction_archive.csv')
    print("Backfill succesvol afgerond!")

if __name__ == "__main__":
    run_backfill()
