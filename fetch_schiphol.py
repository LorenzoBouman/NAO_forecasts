import os
import requests
import numpy as np
import pandas as pd
from datetime import datetime

# =========================================================================
# 1. CONFIGURATIE & GECORRIGEERDE ENDPOINT URL
# =========================================================================
LAT = "52.3081"
LON = "4.7642"

BASE_URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
PARAMS = {
    "latitude": LAT,
    "longitude": LON,
    "hourly": [
        "temperature_2m",
        "wind_speed_10m",
        "wind_direction_10m",
        "wind_gusts_10m"
    ],
    "models": "ecmwf_ifs025",
    "wind_speed_unit": "kn",
    "forecast_days": 8
}

print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Ophalen ECMWF ensemble forecast...")

# =========================================================================
# 2. REQUEST UITVOEREN & VALIDATIE
# =========================================================================
try:
    response = requests.get(BASE_URL, params=PARAMS, timeout=30)
    response.raise_for_status()
    raw_data = response.json()
    print("API-aanroep geslaagd! Verwerken van ensemble-leden...")
except requests.exceptions.RequestException as e:
    raise RuntimeError(f"Fout bij aanroepen Open-Meteo API: {e}")

# =========================================================================
# 3. ENSEMBLE-AGGREGATIE NAAR MODEL FEATURES
# =========================================================================
hourly = raw_data.get("hourly", {})
timestamps = hourly.get("time", [])

df_weather = pd.DataFrame({"forecast_time": pd.to_datetime(timestamps)})

def aggregate_ensemble(hourly_dict, base_name):
    member_cols = [k for k in hourly_dict.keys() if k.startswith(base_name)]
    if not member_cols:
        return None, None
    matrix = np.array([hourly_dict[col] for col in member_cols], dtype=float)
    mean_vals = np.nanmean(matrix, axis=0)
    var_vals = np.nanvar(matrix, axis=0)
    return mean_vals, var_vals

# 1. Temperatuur
temp_mean, temp_var = aggregate_ensemble(hourly, "temperature_2m")
df_weather["temp_slot_mean_mean"] = temp_mean
df_weather["temp_slot_mean_var"]  = temp_var

# Dagelijks maximum temperatuur
df_weather["date"] = df_weather["forecast_time"].dt.date
df_weather["temp_daily_max_mean"] = df_weather.groupby("date")["temp_slot_mean_mean"].transform("max")
df_weather.drop(columns=["date"], inplace=True)

# 2. Windstoten en snelheid
gust_mean, _ = aggregate_ensemble(hourly, "wind_gusts_10m")
df_weather["wind_slot_gust_mean"] = gust_mean

wind_speed_mean, _ = aggregate_ensemble(hourly, "wind_speed_10m")
df_weather["wind_slot_max_mean"]  = wind_speed_mean

# 3. Windrichting & Circulaire variantie
dir_cols = [k for k in hourly.keys() if k.startswith("wind_direction_10m")]
if dir_cols:
    dir_matrix = np.array([hourly[col] for col in dir_cols], dtype=float)
    rads = np.deg2rad(dir_matrix)
    sin_mean = np.nanmean(np.sin(rads), axis=0)
    cos_mean = np.nanmean(np.cos(rads), axis=0)
    
    mean_dir_deg = (np.rad2deg(np.arctan2(sin_mean, cos_mean)) + 360) % 360
    circ_var = 1.0 - np.sqrt(sin_mean**2 + cos_mean**2)
    
    df_weather["wind_slot_dir_mean"] = mean_dir_deg
    df_weather["wind_slot_dir_var"]  = circ_var

# =========================================================================
# 4. HULPFUNCTIE VOOR HET UPDATEN MET DYNAMISCHE KOLOMDETECTIE
# =========================================================================
def update_archive(file_path, new_df, subset_cols):
    if not os.path.exists(file_path):
        print(f"Bestand {file_path} bestaat nog niet, nieuw aangemaakt.")
        new_df[["forecast_time"] + subset_cols].to_csv(file_path, index=False)
        return

    existing_df = pd.read_csv(file_path)

    # Detecteer automatisch hoe de datum/tijdkolom heet in het bestaande bestand
    possible_time_cols = ["forecast_time", "time", "datetime", "date", "timestamp"]
    target_time_col = None
    for col in possible_time_cols:
        if col in existing_df.columns:
            target_time_col = col
            break

    if target_time_col is None:
        target_time_col = existing_df.columns[0]
        print(f"Waarschuwing: Geen bekende tijdkolom gevonden in {file_path}. Eerste kolom gekozen: '{target_time_col}'")

    # Hernoem forecast_time naar de bestaande kolomnaam voor consistentie
    data_to_add = new_df[["forecast_time"] + subset_cols].copy()
    data_to_add.rename(columns={"forecast_time": target_time_col}, inplace=True)

    # Converteer naar datetime voor correcte ontdubbeling en sortering
    existing_df[target_time_col] = pd.to_datetime(existing_df[target_time_col])
    data_to_add[target_time_col] = pd.to_datetime(data_to_add[target_time_col])

    # Combineren, duplicaten filteren (nieuwste waarden behouden) en sorteren
    combined_df = pd.concat([existing_df, data_to_add], ignore_index=True)
    combined_df = combined_df.drop_duplicates(subset=[target_time_col], keep="last")
    combined_df = combined_df.sort_values(target_time_col).reset_index(drop=True)

    # Opslaan
    combined_df.to_csv(file_path, index=False)
    print(f"Succesvol bijgewerkt: {file_path} (Totaal rijen: {len(combined_df)}, tijdkolom: '{target_time_col}')")

# =========================================================================
# 5. WEGSCHRIJVEN NAAR DE 3 SCHIPHOL ARCHIEF BESTANDEN
# =========================================================================
# 1. Temperatuur
temp_cols = ["temp_slot_mean_mean", "temp_slot_mean_var", "temp_daily_max_mean"]
update_archive("schiphol_temperature_archive.csv", df_weather, temp_cols)

# 2. Windrichting
wind_dir_cols = ["wind_slot_dir_mean", "wind_slot_dir_var"]
update_archive("schiphol_wind_direction_archive.csv", df_weather, wind_dir_cols)

# 3. Windsnelheid & Gusts
wind_speed_cols = ["wind_slot_max_mean", "wind_slot_gust_mean"]
update_archive("schiphol_wind_speed_archive.csv", df_weather, wind_speed_cols)

print("Klaar! Alle Schiphol archieven zijn succesvol weggeschreven.")
