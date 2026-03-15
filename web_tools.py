import re
import time
from pathlib import Path

try:
    from selenium import webdriver
    from selenium.webdriver.edge.service import Service
except ImportError:
    webdriver = None

def download_url_as_mhtml(url, output_dir):
    """Downloads a single URL as an MHTML file."""
    if not webdriver:
        print("Selenium not installed. Cannot download URLs.")
        return None

    try:
        print(f"Downloading {url}...")
        options = webdriver.EdgeOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        service = Service()
        driver = webdriver.Edge(service=service, options=options)
        driver.get(url)
        time.sleep(25) # Wait for dynamic content
        mhtml_data = driver.execute_cdp_cmd("Page.captureSnapshot", {"format": "mhtml"})['data']
        driver.quit()

        filename = re.sub(r'[^\w\-_.]', '_', url) + '.mhtml'
        mhtml_path = output_dir / filename
        with open(mhtml_path, "w", encoding="utf-8", newline='') as f:
            f.write(mhtml_data)
        print(f"Successfully saved MHTML to {mhtml_path}")
        return mhtml_path
    except Exception as e:
        print(f"Error downloading URL {url}: {e}")
        return None