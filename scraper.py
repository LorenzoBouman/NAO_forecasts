import os
import re
import csv
import urllib.request
from datetime import datetime
from playwright.sync_api import sync_playwright
import pdfplumber

PORTAL_URL = "https://www.public.nm.eurocontrol.int/PUBPORTAL/gateway/spec/index.html"
CSV_FILE = "nat_tracks_history.csv"

def get_pdf_url():
    print("Launching headless browser...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        # Wait until the network is completely idle to ensure the JS portal is fully loaded
        print("Navigating to Eurocontrol portal...")
        page.goto(PORTAL_URL, wait_until="networkidle", timeout=60000)
        
        print("Waiting for 'Network Plan' element to appear...")
        # Give it up to 30 seconds to render the link
        page.wait_for_selector("text=Network Plan", timeout=30000)
        
        link_element = page.locator("text=Network Plan").first
        pdf_url = link_element.get_attribute("href")
        
        if pdf_url and not pdf_url.startswith("http"):
            pdf_url = page.evaluate("window.location.origin") + pdf_url
            
        browser.close()
        
        if not pdf_url:
            raise ValueError("Failed to extract href from 'Network Plan' link.")
            
        return pdf_url

def parse_nat_tracks(pdf_path):
    print("Parsing PDF for NAT Tracks...")
    eastbound_routes = None
    core_we_route = None
    doc_date = None
    
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            if text and "NAT Tracks" in text:
                print(f"Found NAT Tracks information on Page {i+1}...")
                
                match_eb = re.search(
                    r"Eastbound published tracks are:\s*(.*?)\s*with a predicted core via\s*(.*)", 
                    text, 
                    re.IGNORECASE
                )
                if match_eb:
                    eastbound_routes = match_eb.group(1).strip()
                    core_we_route = match_eb.group(2).strip()
                
                date_match = re.search(r"(\w{3}\s+\d{1,2}\s+\w{3}\s+\d{4})", text)
                if date_match:
                    try:
                        parsed_date = datetime.strptime(date_match.group(1), "%a %d %b %Y")
                        doc_date = parsed_date.strftime("%Y-%m-%d")
                    except ValueError:
                        pass
                break
                
    if not doc_date:
        doc_date = datetime.utcnow().strftime("%Y-%m-%d")
        
    return doc_date, eastbound_routes, core_we_route

def save_to_csv(date, routes, core):
    file_exists = os.path.exists(CSV_FILE)
    with open(CSV_FILE, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Date", "West-to-East Routes", "Core W-E Route"])
        writer.writerow([date, routes, core])
    print(f"Successfully appended data to {CSV_FILE}")

def main():
    # Remove the broad try-except so GitHub Actions can detect failures
    pdf_url = get_pdf_url()
    
    pdf_filename = "network_plan.pdf"
    print(f"Target PDF URL: {pdf_url}")
    urllib.request.urlretrieve(pdf_url, pdf_filename)
    
    doc_date, eb_routes, core_we = parse_nat_tracks(pdf_filename)
    
    if eb_routes and core_we:
        print(f"Extracted: Date={doc_date} | Routes={eb_routes} | Core={core_we}")
        save_to_csv(doc_date, eb_routes, core_we)
    else:
        # Throw an error if we found the PDF but could not extract the NAT tracks
        raise ValueError("Could not locate or parse the NAT tracks pattern in the downloaded PDF.")

if __name__ == "__main__":
    main()
