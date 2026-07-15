import os
import re
import urllib.request
import pdfplumber
import csv
from datetime import datetime

# 1. Configuration & Directories
PORTAL_URL = "https://www.public.nm.eurocontrol.int/PUBPORTAL/gateway/spec/"
PDF_TEMP = "temp_network_plan.pdf"
CSV_PATH = "eurocontrol_history.csv"

os.makedirs("data", exist_ok=True)

import json

# Portal configurations
PORTAL_ROOT = "https://www.public.nm.eurocontrol.int/PUBPORTAL/gateway/spec/"
PORTAL_INDEX = "https://www.public.nm.eurocontrol.int/PUBPORTAL/gateway/spec/index.html"

def find_daily_pdf_url():
    """
    Tries multiple entry points on the Eurocontrol portal and uses flexible regex 
    to extract the dynamic daily Initial Network Plan PDF link.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5'
    }

    # We test both URLs since Eurocontrol sometimes routes deep configurations differently
    target_urls = [PORTAL_INDEX, PORTAL_ROOT]
    
    for url in target_urls:
        print(f"Scanning portal page: {url}...")
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as response:
                html_content = response.read().decode('utf-8', errors='ignore')
                
                # Flexible regex searching for the daily resource directory structure
                # This matches formats like: _res/20260714/20260714-180449.pdf
                pdf_pattern = re.compile(r'_res/\d{8}/\d{8}-\d{6}\.pdf', re.IGNORECASE)
                matches = pdf_pattern.findall(html_content)
                
                if matches:
                    # Select the most recent matched directory link
                    relative_pdf_path = matches[-1].lstrip('/')
                    full_pdf_url = f"{PORTAL_ROOT}{relative_pdf_path}?APPID=initial_network_plan"
                    print(f"Successfully discovered today's dynamic PDF URL: {full_pdf_url}")
                    return full_pdf_url
                    
        except Exception as e:
            print(f"Warning: Failed scanning {url} due to error: {e}")
            continue

    # --- DIAGNOSTIC FALLBACK ---
    # If both fails, let's print out the landing page structure to help debug
    print("\n--- Scraper Diagnostic Report ---")
    print(f"Attempting to fetch raw source of {PORTAL_INDEX} for debugging...")
    try:
        req = urllib.request.Request(PORTAL_INDEX, headers=headers)
        with urllib.request.urlopen(req) as response:
            debug_html = response.read().decode('utf-8', errors='ignore')
            print("HTML Length:", len(debug_html))
            print("Beginning of Page Source (First 1000 chars):")
            print(debug_html[:1000])
            
            # Print any scripts or configuration file matches found on the page
            js_files = re.findall(r'src=["\'](.*?)["\']', debug_html)
            if js_files:
                print("\nDiscovered JavaScript files running on this page:")
                for js in js_files[:5]:
                    print(f" - {js}")
    except Exception as debug_err:
        print("Could not generate diagnostic HTML source:", debug_err)
    print("---------------------------------\n")

    raise ValueError("Could not resolve dynamic PDF path from any portal landing page.")
def legacy_html_fallback():
    headers = {'User-Agent': 'Mozilla/5.0'}
    req = urllib.request.Request(PORTAL_URL, headers=headers)
    with urllib.request.urlopen(req) as response:
        html_content = response.read().decode('utf-8', errors='ignore')
    pattern = re.compile(r'_res/\d{8}/\d{8}-\d{6}\.pdf')
    matches = pattern.findall(html_content)
    if not matches:
        raise ValueError("Could not resolve dynamic PDF path from API or HTML fallback.")
    return f"{PORTAL_URL}{matches[-1]}?APPID=initial_network_plan"

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
        test_pdf_url = "https://www.public.nm.eurocontrol.int/PUBPORTAL/gateway/spec/_res/20260715/20260715-180949.pdf?APPID=initial_network_plan"
        pdf_url = find_daily_pdf_url()
        download_pdf(test_pdf_url, PDF_TEMP)
        records = extract_and_parse(PDF_TEMP)
        if records:
            save_to_database(records, CSV_PATH)
        else:
            print("No records matched the scraping rules today.")
    except Exception as e:
        print(f"Error executing scraper: {e}")
        raise e
    finally:
        if os.path.exists(PDF_TEMP):
            os.remove(PDF_TEMP)

if __name__ == "__main__":
    main()
