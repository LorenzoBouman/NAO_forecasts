import os
import requests
import pandas as pd
from datetime import datetime

# Coördinaten voor Schiphol
LAT = "52.3081"
LON = "4.7642"

# 自由 URL gecorrigeerd: 'models=' is volledig weggehaald zodat hij automatisch het gratis GEFS-ensemble pakt
URL = f"https://ensemble-api.open-meteo.com/v1/ensemble?latitude={LAT}&longitude={LON}&hourly=temperature_2m,wind_speed_10m,wind_direction_10m&forecast_days=8"

def archive_schiphol_weather():
    try:
        # 1. Haal de JSON data op van Open-Meteo
        response = requests.get(URL)
        data = response.json()
        
        if "hourly" not in data:
            print("Geen data ontvangen van API.")
            return
            
        # 2. Laad de uren-data in een Pandas DataFrame
        hourly_data = data["hourly"]
        df_hourly = pd.DataFrame(hourly_data)
        
        # Converteer de tijd-kolom naar echte datums
        df_hourly['time'] = pd.to_datetime(df_hourly['time'])
        df_hourly['forecast_date'] = df_hourly['time'].dt.strftime('%Y-%m-%d')
        
        # Definieer de initialisatiedatum (Vandaag)
        init_date = datetime.utcnow().strftime('%Y-%m-%d')
        
        # 3. Splits en verwerk de drie numerieke variabelen
        variables = {
            'temperature_2m': 'schiphol_temperature_archive.csv',
            'wind_speed_10m': 'schiphol_wind_speed_archive.csv',
            'wind_direction_10m': 'schiphol_wind_direction_archive.csv'
        }
        
        for var_prefix, filename in variables.items():
            # Filter alle kolommen (members) die bij deze specifieke variabele horen (bijv. temperature_2m_member1)
            member_cols = [col for col in df_hourly.columns if col.startswith(var_prefix)]
            
            if not member_cols:
                print(f"Waarschuwing: Geen kolommen gevonden voor {var_prefix}")
                continue
                
            # Groepeer de uren naar daggemiddelden per ensemble member
            df_daily_members = df_hourly.groupby('forecast_date')[member_cols].mean()
            
            # Bereken de statistieken over de members heen per dag
            archive_chunk = pd.DataFrame()
            archive_chunk['interval_low'] = df_daily_members.min(axis=1)
            archive_chunk['interval_high'] = df_daily_members.max(axis=1)
            archive_chunk['ensemble_mean'] = df_daily_members.mean(axis=1)
            archive_chunk['ensemble_variance'] = df_daily_members.var(axis=1)
            archive_chunk = archive_chunk.reset_index()
            
            # Voeg initialisatie en lead-time toe
            archive_chunk['init_date'] = init_date
            archive_chunk['forecast_date'] = pd.to_datetime(archive_chunk['forecast_date'])
            archive_chunk['lead_time_days'] = (archive_chunk['forecast_date'] - pd.to_datetime(init_date)).dt.days
            
            # Filter zodat we exact lead days 1 tot en met 7 bewaren
            archive_chunk = archive_chunk[(archive_chunk['lead_time_days'] >= 1) & (archive_chunk['lead_time_days'] <= 7)]
            
            # Zet kolommen in de gewenste vaste volgorde
            archive_chunk['forecast_date'] = archive_chunk['forecast_date'].dt.strftime('%Y-%m-%d')
            final_cols = ['init_date', 'forecast_date', 'lead_time_days', 'interval_low', 'interval_high', 'ensemble_mean', 'ensemble_variance']
            archive_chunk = archive_chunk[final_cols].sort_values('lead_time_days')
            
            # 4. Opslaan of Toevoegen (Append) aan het juiste CSV-bestand
            if not os.path.exists(filename):
                archive_chunk.to_csv(filename, index=False)
                print(f"Nieuw bestand aangemaakt met kolommen: {filename}")
            else:
                master_df = pd.read_csv(filename)
                if init_date in master_df['init_date'].astype(str).values:
                    print(f"Data voor run {init_date} al aanwezig in {filename}. Overslaan.")
                else:
                    archive_chunk.to_csv(filename, mode='a', header=False, index=False)
                    print(f"Data succesvol toegevoegd aan {filename}")
                    
    except Exception as e:
        print(f"Fout opgetreden tijdens het verwerken: {e}")

if __name__ == "__main__":
    archive_schiphol_weather()
