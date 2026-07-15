import os
import re
import urllib.request
import pdfplumber
import csv
from datetime import datetime

# 1. Configuration & Directories
PORTAL_URL = "https://www.public.nm.eurocontrol.int/PUBPORTAL/gateway/spec/"
PDF_TEMP = "temp_network_plan.pdf"
CSV_PATH = "data/eurocontrol_history.csv"

os.makedirs("data", exist_ok=True)

def find_daily_pdf_url():
    """
    Parses the dynamic HTML source of the Eurocontrol portal to construct the
    exact transient daily PDF URL.
    """
    print(f"Fetching portal index from {PORTAL_URL}...")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    req = urllib.request.Request(PORTAL_URL, headers=headers)
    
    with urllib.request.urlopen(req) as response:
        html_content = response.read().decode('utf-8', errors='ignore')

    # Locate resource folders (structured as _res/YYYYMMDD/...)
    # Example matches: _res/20260715/20260715-180449.pdf
    pattern = re.compile(r'_res/\d{8}/\d{8}-\d{6}\.pdf')
    matches = pattern.findall(html_content)
    
    if not matches:
        raise ValueError("Could not find the dynamic Daily PDF path in the portal HTML.")
        
    # Grab the most recent document match
    relative_pdf_path = matches[-1]
    full_pdf_url = f"{PORTAL_URL}{relative_pdf_path}?APPID=initial_network_plan"
    print(f"Discovered today's dynamic PDF URL: {full_pdf_url}")
    return full_pdf_url

def download_pdf(url, dest):
    print(f"Downloading daily plan...")
    headers = {'User-Agent': 'Mozilla/5.0'}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as response, open(dest, 'wb') as out_file:
        out_file.write(response.read())

def extract_and_parse(pdf_path):
    print("Parsing PDF content...")
    records = []
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    
    # Matches airport regulations (e.g., "EGLF: Zero-rate...") or airspace sectors
    pattern = re.compile(r"([A-Z]{4}):\s*(.*)")

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            text = page.extract_text()
            if not text:
                continue
                
            for line in text.split('\n'):
                match = pattern.search(line)
                if match:
                    code = match.group(1)
                    details = match.group(2)
                    records.append({
                        "Date": today_str,
                        "Page": page_num,
                        "Code": code,
                        "Details": details.strip()
                    })
    return records

def save_to_database(new_records, csv_path):
    file_exists = os.path.exists(csv_path)
    headers = ["Date", "Page", "Code", "Details"]
    
    with open(csv_path, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        if not file_exists:
            writer.writeheader()
        writer.writerows(new_records)
    print(f"Successfully wrote {len(new_records)} records to {csv_path}")

def main():
    try:
        test_pdf_url = https://www.public.nm.eurocontrol.int/PUBPORTAL/gateway/spec/_res/20260715/20260715-180949.pdf?APPID=initial_network_plan
        pdf_url = find_daily_pdf_url()
        download_pdf(test_pdf_url, PDF_TEMP)
        records = extract_and_parse(PDF_TEMP)
        if records:
            save_to_database(records, CSV_PATH)
        else:
            print("No records matched the scraping rules today.")
    except Exception as e:
        print(f"Error executing scraper: {e}")
    finally:
        if os.path.exists(PDF_TEMP):
            os.remove(PDF_TEMP)

if __name__ == "__main__":
    main()
