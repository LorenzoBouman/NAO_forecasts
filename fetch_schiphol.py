import os
import requests
import pandas as pd
import numpy as np
from datetime import datetime

LAT = "52.3081"
LON = "4.7642"
# 🟢 URL AANGEPAST: wind_gusts_10m toegevoegd en wind_speed_unit staat nu op 'kn' (knopen)
URL = f"https://ensemble-api.open-meteo.com/v1/ensemble?latitude={LAT}&longitude={LON}&hourly=temperature_2m,wind_speed_10m,wind_direction_10m,wind_gusts_10m&wind_speed_unit=kn&forecast_days=8"

def process_ensemble_stats(df_members, init_date):
    """Hulpfunctie om min, max, mean en var te berekenen over de members heen"""
    stats = pd.DataFrame(index=df_members.index)
    stats['low'] = df_members.min(axis=1)
    stats['high'] = df_members.max(axis=1)
    stats['mean'] = df_members.mean(axis=1)
    stats['var'] = df_members.var(axis=1)
    stats = stats.reset_index().rename(columns={'index': 'forecast_date'})
    stats['init_date'] = init_date
    stats['lead_time_days'] = (pd.to_datetime(stats['forecast_date']) - pd.to_datetime(init_date)).dt.days
    return stats[(stats['lead_time_days'] >= 1) & (stats['lead_time_days'] <= 7)]

def save_to_csv(df_chunk, filename):
    """Hulpfunctie om data netjes weg te schrijven of te appenden"""
    if not os.path.exists(filename):
        df_chunk.to_csv(filename, index=False)
        print(f"Nieuw bestand aangemaakt: {filename}")
    else:
        master_df = pd.read_csv(filename)
        init_date = df_chunk['init_date'].iloc[0]
        if init_date in master_df['init_date'].astype(str).values:
            print(f"Data voor run {init_date} al aanwezig in {filename}. Overslaan.")
        else:
            df_chunk.to_csv(filename, mode='a', header=False, index=False)
            print(f"Data succesvol toegevoegd aan {filename}")

def archive_schiphol_segmented():
    try:
        response = requests.get(URL)
        df_hourly = pd.DataFrame(response.json()["hourly"])
        df_hourly['time'] = pd.to_datetime(df_hourly['time'])
        df_hourly['forecast_date'] = df_hourly['time'].dt.strftime('%Y-%m-%d')
        df_hourly['hour'] = df_hourly['time'].dt.hour
        
        init_date = datetime.utcnow().strftime('%Y-%m-%d')
        
        # Dynamisch ensemble-members detecteren
        suffixes = [c.replace("temperature_2m", "") for c in df_hourly.columns if c.startswith("temperature_2m")]
        
        if not suffixes:
            print("Fout: Geen ensemble kolommen gevonden in de data van Open-Meteo.")
            return
        
        # Tijdsblokken definiëren
        df_morning = df_hourly[(df_hourly['hour'] >= 6) & (df_hourly['hour'] < 12)]
        df_afternoon = df_hourly[(df_hourly['hour'] >= 12) & (df_hourly['hour'] < 18)]
        df_evening = df_hourly[(df_hourly['hour'] >= 18) & (df_hourly['hour'] < 24)]
        
        # Dataframes voor de berekeningen per member
        temp_m_mean, temp_a_mean, temp_e_mean, temp_max = pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
        wind_m_max, wind_a_max, wind_e_max = pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
        wind_gust_m_max, wind_gust_a_max, wind_gust_e_max = pd.DataFrame(), pd.DataFrame(), pd.DataFrame() # 🟢 Toegevoegd
        dir_m_avg, dir_a_avg, dir_e_avg = pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

        for i, suff in enumerate(suffixes):
            t_col = f"temperature_2m{suff}"
            ws_col = f"wind_speed_10m{suff}"
            wd_col = f"wind_direction_10m{suff}"
            wg_col = f"wind_gusts_10m{suff}" # 🟢 Toegevoegd
            m_id = f"m{i}"
            
            if t_col in df_hourly.columns and ws_col in df_hourly.columns and wd_col in df_hourly.columns:
                # --- 1. TEMPERATUUR ---
                temp_m_mean[m_id] = df_morning.groupby('forecast_date')[t_col].mean()
                temp_a_mean[m_id] = df_afternoon.groupby('forecast_date')[t_col].mean()
                temp_e_mean[m_id] = df_evening.groupby('forecast_date')[t_col].mean()
                temp_max[m_id] = df_hourly.groupby('forecast_date')[t_col].max()
                
                # --- 2. WINDSNELHEID ---
                wind_m_max[m_id] = df_morning.groupby('forecast_date')[ws_col].max()
                wind_a_max[m_id] = df_afternoon.groupby('forecast_date')[ws_col].max()
                wind_e_max[m_id] = df_evening.groupby('forecast_date')[ws_col].max()
                
                # --- 3. WINDSTOTEN 🟢 ---
                if wg_col in df_hourly.columns:
                    wind_gust_m_max[m_id] = df_morning.groupby('forecast_date')[wg_col].max()
                    wind_gust_a_max[m_id] = df_afternoon.groupby('forecast_date')[wg_col].max()
                    wind_gust_e_max[m_id] = df_evening.groupby('forecast_date')[wg_col].max()
                
                # --- 4. WINDRICHTING (Trigonometrisch) ---
                for df_p, target_df in [(df_morning, dir_m_avg), (df_afternoon, dir_a_avg), (df_evening, dir_e_avg)]:
                    rad = np.deg2rad(df_p[wd_col])
                    sin_mean = np.sin(rad).groupby(df_p['forecast_date']).mean()
                    cos_mean = np.cos(rad).groupby(df_p['forecast_date']).mean()
                    target_df[m_id] = (np.rad2deg(np.arctan2(sin_mean, cos_mean)) % 360)

        # --- SAMENVATTEN ---
        # A. Temperatuur CSV
        t_m = process_ensemble_stats(temp_m_mean, init_date).set_index('forecast_date')
        t_a = process_ensemble_stats(temp_a_mean, init_date).set_index('forecast_date')
        t_e = process_ensemble_stats(temp_e_mean, init_date).set_index('forecast_date')
        t_x = process_ensemble_stats(temp_max, init_date).set_index('forecast_date')
        
        t_final = pd.DataFrame(index=t_m.index)
        t_final['init_date'] = t_m['init_date']
        t_final['lead_time_days'] = t_m['lead_time_days']
        for df_part, p in [(t_m, 'morning_mean'), (t_a, 'afternoon_mean'), (t_e, 'evening_mean'), (t_x, 'daily_max')]:
            for stat in ['low', 'high', 'mean', 'var']:
                t_final[f'{p}_{stat}'] = df_part[stat]
        t_final = t_final.reset_index()
        t_final = t_final[['init_date', 'forecast_date', 'lead_time_days'] + [c for c in t_final.columns if c not in ['init_date', 'forecast_date', 'lead_time_days']]]
        save_to_csv(t_final.sort_values('lead_time_days'), 'schiphol_temperature_archive.csv')

        # B. Windsnelheid & Windstoten CSV 🟢
        w_m = process_ensemble_stats(wind_m_max, init_date).set_index('forecast_date')
        w_a = process_ensemble_stats(wind_a_max, init_date).set_index('forecast_date')
        w_e = process_ensemble_stats(wind_e_max, init_date).set_index('forecast_date')
        
        w_final = pd.DataFrame(index=w_m.index)
        w_final['init_date'] = w_m['init_date']
        w_final['lead_time_days'] = w_m['lead_time_days']
        
        # Normale windsnelheid krijgt alle statistieken
        for df_part, p in [(w_m, 'morning_max'), (w_a, 'afternoon_max'), (w_e, 'evening_max')]:
            for stat in ['low', 'high', 'mean', 'var']:
                w_final[f'{p}_{stat}'] = df_part[stat]
                
        # Windstoten krijgen ALLEEN het ensemble-gemiddelde (_mean)
        if not wind_gust_m_max.empty:
            wg_m = process_ensemble_stats(wind_gust_m_max, init_date).set_index('forecast_date')
            wg_a = process_ensemble_stats(wind_gust_a_max, init_date).set_index('forecast_date')
            wg_e = process_ensemble_stats(wind_gust_e_max, init_date).set_index('forecast_date')
            
            w_final['morning_gust_mean'] = wg_m['mean']
            w_final['afternoon_gust_mean'] = wg_a['mean']
            w_final['evening_gust_mean'] = wg_e['mean']
                
        w_final = w_final.reset_index()
        w_final = w_final[['init_date', 'forecast_date', 'lead_time_days'] + [c for c in w_final.columns if c not in ['init_date', 'forecast_date', 'lead_time_days']]]
        save_to_csv(w_final.sort_values('lead_time_days'), 'schiphol_wind_speed_archive.csv')

        # C. Windrichting CSV
        d_m = process_ensemble_stats(dir_m_avg, init_date).set_index('forecast_date')
        d_a = process_ensemble_stats(dir_a_avg, init_date).set_index('forecast_date')
        d_e = process_ensemble_stats(dir_e_avg, init_date).set_index('forecast_date')
        
        d_final = pd.DataFrame(index=d_m.index)
        d_final['init_date'] = d_m['init_date']
        d_final['lead_time_days'] = d_m['lead_time_days']
        for df_part, p in [(d_m, 'morning_dir'), (d_a, 'afternoon_dir'), (d_e, 'evening_dir')]:
            for stat in ['low', 'high', 'mean', 'var']:
                d_final[f'{p}_{stat}'] = df_part[stat]
                
        d_final = d_final.reset_index()
        d_final = d_final[['init_date', 'forecast_date', 'lead_time_days'] + [c for c in d_final.columns if c not in ['init_date', 'forecast_date', 'lead_time_days']]]
        save_to_csv(d_final.sort_values('lead_time_days'), 'schiphol_wind_direction_archive.csv')

    except Exception as e:
        print(f"Fout: {e}")

if __name__ == "__main__":
    archive_schiphol_segmented()
