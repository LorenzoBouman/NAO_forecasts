import os
import re
import urllib.request
from playwright.sync_api import sync_playwright
import pdfplumber

PORTAL_URL = "https://www.public.nm.eurocontrol.int/PUBPORTAL/gateway/spec/index.html"

def get_pdf_url():
    print("Launching headless browser...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(PORTAL_URL)
        
        # Wait for the "Initial Network Plan" portlet and the "Network Plan" link to load
        print("Waiting for 'Network Plan' element to appear...")
        page.wait_for_selector("text=Network Plan")
        
        # Extract the href attribute of the 'Network Plan' element
        link_element = page.locator("text=Network Plan").first
        pdf_url = link_element.get_attribute("href")
        
        # If the href is relative, resolve it against the base URL
        if pdf_url and not pdf_url.startswith("http"):
            pdf_url = page.evaluate("window.location.origin") + pdf_url
            
        browser.close()
        return pdf_url

def parse_nat_tracks(pdf_path):
    print("Parsing PDF for NAT Tracks...")
    eastbound_routes = None
    core_we_route = None
    
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            if text and "NAT Tracks" in text:
                print(f"Found NAT Tracks information on Page {i+1}...")
                
                # Regex match for Eastbound routes and core
                # Example: "Eastbound published tracks are: PIKIL 56N to LIMRI 52N with a predicted core via DOGAL 54N"
                match_eb = re.search(
                    r"Eastbound published tracks are:\s*(.*?)\s*with a predicted core via\s*(.*)", 
                    text, 
                    re.IGNORECASE
                )
                if match_eb:
                    eastbound_routes = match_eb.group(1).strip()
                    core_we_route = match_eb.group(2).strip()
                    break
                    
    return eastbound_routes, core_we_route

def main():
    try:
        pdf_url = get_pdf_url()
        if not pdf_url:
            print("Error: Could not retrieve the Network Plan PDF URL.")
            return
        
        print(f"Target PDF URL found: {pdf_url}")
        
        # Download the PDF
        pdf_filename = "network_plan.pdf"
        print("Downloading PDF...")
        urllib.request.urlretrieve(pdf_url, pdf_filename)
        print("Download complete.")
        
        # Parse NAT Tracks
        eb_routes, core_we = parse_nat_tracks(pdf_filename)
        
        if eb_routes and core_we:
            print("\n--- EXTRACTED DATA ---")
            print(f"West-to-East Routes: {eb_routes}")
            print(f"Core W-E Route:      {core_we}")
            print("----------------------\n")
            
            # Save output to a file (optional - useful for GitHub Action artifacts)
            with open("nat_tracks_summary.txt", "w") as f:
                f.write(f"Date: {pdf_url.split('/')[-2]}\n")
                f.write(f"West-to-East Routes: {eb_routes}\n")
                f.write(f"Core W-E Route: {core_we}\n")
        else:
            print("Could not locate or parse the NAT tracks pattern in the downloaded PDF.")
            
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
