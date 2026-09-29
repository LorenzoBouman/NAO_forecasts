import os
import requests
import pandas as pd
import numpy as np
from datetime import datetime

LAT = "52.3081"
LON = "4.7642"

# past_days=11 zorgt voor een ruime buffer voor 2026-09-23 en 2026-09-24
URL = (
    f"https://ensemble-api.open-meteo.com/v1/ensemble?"
    f"latitude={LAT}&longitude={LON}&"
    f"hourly=temperature_2m,wind_speed_10m,wind_direction_10m,wind_gusts_10m&"
    f"models=ecmwf_ifs025&wind_speed_unit=kn&"
    f"past_days=11&forecast_days=8"
)

TARGET_INIT_DATES = ["2026-09-22", "2026-09-23"]

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
    
    stats = pd.DataFrame(index=df_members.index)
    stats['low'] = (mean_deg - circ_std_deg) % 360
    stats['high'] = (mean_deg + circ_std_deg) % 360
    stats['mean'] = mean_deg
    stats['var'] = circ_var
    stats = stats.reset_index().rename(columns={'index': 'forecast_date'})
    stats['init_date'] = init_date
    stats['lead_time_days'] = (pd.to_datetime(stats['forecast_date']) - pd.to_datetime(init_date)).dt.days
    return stats[(stats['lead_time_days'] >= 1) & (stats['lead_time_days'] <= 7)]

def fill_only_missing(new_df, filename):
    if not os.path.exists(filename):
        print(f"{filename} niet gevonden.")
        return
        
    # 1. Lees CSV in en dwing alle lege strings/spaties expliciet af als NaN
    master_df = pd.read_csv(filename, keep_default_na=True, na_values=['', ' ', 'nan', 'NaN'])
    
    key_cols = ['init_date', 'forecast_date']
    
    # 2. Filter new_df op rijen die ook daadwerkelijk numerieke data bevatten
    valid_new_df = new_df.dropna(subset=[c for c in new_df.columns if c not in key_cols], how='all')
    
    # 3. Koppel op basis van de unieke sleutel
    master_indexed = master_df.set_index(key_cols)
    new_indexed = valid_new_df.set_index(key_cols)
    
    # Alleen lege cellen overschrijven met de nieuw berekende data
    master_indexed.update(new_indexed, overwrite=False)
    repaired_df = master_indexed.combine_first(new_indexed).reset_index()
    
    # 4. Consistentie van lead_time_days waarborgen en sorteren
    repaired_df['lead_time_days'] = (
        pd.to_datetime(repaired_df['forecast_date']) - pd.to_datetime(repaired_df['init_date'])
    ).dt.days
    repaired_df = repaired_df.sort_values(by=['init_date', 'lead_time_days']).reset_index(drop=True)
    
    repaired_df.to_csv(filename, index=False)
    print(f"Reparatie voltooid voor: {filename}")

def run_repair():
    print("Ophalen data met past_days=11...")
    res = requests.get(URL, timeout=30)
    res.raise_for_status()
    df_hourly = pd.DataFrame(res.json()["hourly"])
    df_hourly['time'] = pd.to_datetime(df_hourly['time'])
    df_hourly['forecast_date'] = df_hourly['time'].dt.strftime('%Y-%m-%d')
    df_hourly['hour'] = df_hourly['time'].dt.hour
    
    suffixes = [c.replace("temperature_2m", "") for c in df_hourly.columns if c.startswith("temperature_2m")]
    
    df_morning = df_hourly[(df_hourly['hour'] >= 6) & (df_hourly['hour'] < 12)]
    df_afternoon = df_hourly[(df_hourly['hour'] >= 12) & (df_hourly['hour'] < 18)]
    df_evening = df_hourly[(df_hourly['hour'] >= 18) & (df_hourly['hour'] < 24)]

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

    t_chunks, w_chunks, d_chunks = [], [], []

    for target_init in TARGET_INIT_DATES:
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
        t_chunks.append(t_final.reset_index())

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
        w_chunks.append(w_final.reset_index())

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
        d_chunks.append(d_final.reset_index())

    # Voer gerichte invulling uit
    fill_only_missing(pd.concat(t_chunks, ignore_index=True), 'schiphol_temperature_archive.csv')
    fill_only_missing(pd.concat(w_chunks, ignore_index=True), 'schiphol_wind_speed_archive.csv')
    fill_only_missing(pd.concat(d_chunks, ignore_index=True), 'schiphol_wind_direction_archive.csv')

    # =========================================================================
    # DEBUG CONTROLE IN ACTIONS LOGS
    # =========================================================================
    check_temp = pd.read_csv('schiphol_temperature_archive.csv', keep_default_na=True, na_values=['', ' ', 'nan', 'NaN'])
    sub = check_temp[check_temp['init_date'].isin(TARGET_INIT_DATES)]
    print("\n--- STATUS CHECK IN CSV (init_date 2026-09-22 en 2026-09-23) ---")
    print(sub[['init_date', 'forecast_date', 'lead_time_days', 'morning_mean_mean']].to_string(index=False))

if __name__ == "__main__":
    run_repair()
