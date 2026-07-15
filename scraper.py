import os
import re
import csv
from datetime import datetime
from playwright.sync_api import sync_playwright
import pdfplumber

PORTAL_URL = "https://www.public.nm.eurocontrol.int/PUBPORTAL/gateway/spec/index.html"
CSV_FILE = "nat_tracks_history.csv"

def download_network_plan():
    print("Launching headless browser...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        print("Navigating to Eurocontrol portal...")
        page.goto(PORTAL_URL, wait_until="networkidle", timeout=60000)
        
        print("Waiting for 'Network Plan' link to become active...")
        # We target the actual anchor link (a tag) containing "Network Plan" to bypass the header
        link_selector = "a:has-text('Network Plan')"
        page.wait_for_selector(link_selector, timeout=30000)
        
        # Set up a listener for the dynamic browser download event
        print("Clicking the link and waiting for download stream...")
        with page.expect_download(timeout=30000) as download_info:
            page.locator(link_selector).first.click()
            
        download = download_info.value
        pdf_filename = "network_plan.pdf"
        
        # Save the dynamically downloaded file
        download.save_as(pdf_filename)
        print(f"File successfully downloaded and saved to: {pdf_filename}")
        
        browser.close()
        return pdf_filename

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
                
                # Regex match for Eastbound routes and core
                match_eb = re.search(
                    r"Eastbound published tracks are:\s*(.*?)\s*with a predicted core via\s*(.*)", 
                    text, 
                    re.IGNORECASE
                )
                if match_eb:
                    eastbound_routes = match_eb.group(1).strip()
                    core_we_route = match_eb.group(2).strip()
                
                # Extract date from the footer (e.g., "Wed 15 Jul 2026")
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
    # Download via Playwright click event
    pdf_filename = download_network_plan()
    
    # Parse the downloaded PDF
    doc_date, eb_routes, core_we = parse_nat_tracks(pdf_filename)
    
    if eb_routes and core_we:
        print(f"Extracted: Date={doc_date} | Routes={eb_routes} | Core={core_we}")
        save_to_csv(doc_date, eb_routes, core_we)
    else:
        raise ValueError("Could not locate or parse the NAT tracks pattern in the downloaded PDF.")

if __name__ == "__main__":
    main()
