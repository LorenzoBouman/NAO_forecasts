import os
import pandas as pd

# The exact URL/file path you are using
FORECAST_URL = "https://ftp.cpc.ncep.noaa.gov/cwlinks/norm.daily.nao.gefs.z500.120days.csv"
MASTER_LOG_FILE = "nao_7day_intervals_archive.csv"

def archive_intervals_from_tidy_csv():
    try:
        # 1. Load the dataset
        df = pd.read_csv(FORECAST_URL)
        df.columns = df.columns.str.strip()
        
        # 2. Find the absolute latest forecast run date (e.g., 2026-07-08)
        latest_run_date = df['time'].max()
        
        # 3. Isolate that run, and grab only lead times 1 through 7 days ahead
        latest_run_df = df[df['time'] == latest_run_date]
        seven_day_forecasts = latest_run_df[(latest_run_df['lead'] >= 1) & (latest_run_df['lead'] <= 7)].copy()
        
        if seven_day_forecasts.empty:
            print(f"No forecast data found for run date: {latest_run_date}")
            return
            
        # 4. Collapse the 31 ensemble members into min, max, and mean intervals
        archive_chunk = seven_day_forecasts.groupby(['time', 'valid_time', 'lead'])['nao_index'].agg(
            interval_low='min',
            interval_high='max',
            ensemble_mean='mean'
        ).reset_index()
        
        # Rename columns to be perfectly intuitive for your archive
        archive_chunk = archive_chunk.rename(columns={
            'time': 'init_date',
            'valid_time': 'forecast_date',
            'lead': 'lead_time_days'
        })
        
        # 5. Save/Append to your permanent dataset
        if not os.path.exists(MASTER_LOG_FILE):
            archive_chunk.to_csv(MASTER_LOG_FILE, index=False)
            print(f"Created fresh archive with intervals for run: {latest_run_date}")
        else:
            master_df = pd.read_csv(MASTER_LOG_FILE)
            if latest_run_date in master_df['init_date'].astype(str).values:
                print(f"Forecast run {latest_run_date} is already archived. Skipping.")
            else:
                archive_chunk.to_csv(MASTER_LOG_FILE, mode='a', header=False, index=False)
                print(f"Successfully logged 7-day prediction intervals for run: {latest_run_date}")
                
    except Exception as e:
        print(f"Error processing data: {e}")

if __name__ == "__main__":
    archive_intervals_from_tidy_csv()
