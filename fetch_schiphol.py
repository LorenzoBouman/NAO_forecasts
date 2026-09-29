import requests
import numpy as np
import pandas as pd
from datetime import datetime

# =========================================================================
# 1. CONFIGURATIE & GECORRIGEERDE ENDPOINT URL
# =========================================================================
LAT = "52.3081"
LON = "4.7642"

# models=ecmwf_ifs025 lost de 'best_match is not supported' error op
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

# Hulpfunctie om alle ensemble-leden voor een variabele te groeperen en aggregeren
def aggregate_ensemble(hourly_dict, base_name):
    # Zoek alle kolommen zoals 'temperature_2m_member01', etc.
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

# 2. Windstoten (Gusts)
gust_mean, _ = aggregate_ensemble(hourly, "wind_gusts_10m")
df_weather["wind_slot_gust_mean"] = gust_mean

# 3. Windsnelheid
wind_speed_mean, _ = aggregate_ensemble(hourly, "wind_speed_10m")
df_weather["wind_slot_max_mean"]  = wind_speed_mean

# 4. Windrichting & Variantie in windrichting (circulaire variantie)
dir_cols = [k for k in hourly.keys() if k.startswith("wind_direction_10m")]
if dir_cols:
    dir_matrix = np.array([hourly[col] for col in dir_cols], dtype=float)
    # Converteer naar radialen voor correcte gemiddelde richting en variantie
    rads = np.deg2rad(dir_matrix)
    sin_mean = np.nanmean(np.sin(rads), axis=0)
    cos_mean = np.nanmean(np.cos(rads), axis=0)
    
    mean_dir_deg = (np.rad2deg(np.arctan2(sin_mean, cos_mean)) + 360) % 360
    # Circulaire variantie: 1 - R (waarbij R de vectorlengte is)
    circ_var = 1.0 - np.sqrt(sin_mean**2 + cos_mean**2)
    
    df_weather["wind_slot_dir_mean"] = mean_dir_deg
    df_weather["wind_slot_dir_var"]  = circ_var

# Dagelijks maximum temperatuur berekenen per datum
df_weather["date"] = df_weather["forecast_time"].dt.date
daily_max = df_weather.groupby("date")["temp_slot_mean_mean"].transform("max")
df_weather["temp_daily_max_mean"] = daily_max

# =========================================================================
# 4. CONTROLE & PREVIEW
# =========================================================================
print(f"Dataframe succesvol opgebouwd: {df_weather.shape[0]} uur-records.")
display_cols = [
    "forecast_time",
    "temp_slot_mean_mean",
    "wind_slot_gust_mean",
    "wind_slot_dir_mean",
    "wind_slot_dir_var"
]
print(df_weather[display_cols].head(10).to_string(index=False))
