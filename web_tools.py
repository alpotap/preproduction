"""Downloads web pages to MHTML and extracts cleaned HTML text when needed."""

import os
import re
import time
import email
from pathlib import Path
from bs4 import BeautifulSoup

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

    headless = os.getenv("EDGE_HEADLESS", "true").strip().lower() not in {"false", "0", "no"}
    try:
        wait_seconds = int(os.getenv("EDGE_WAIT_SECONDS", "25"))
    except ValueError:
        wait_seconds = 25

    driver = None
    try:
        print(f"Downloading {url}...")
        options = webdriver.EdgeOptions()
        if headless:
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        service = Service()
        driver = webdriver.Edge(service=service, options=options)
        driver.get(url)
        time.sleep(wait_seconds)  # Wait for dynamic content

        # Remove UI drawer/navigation before snapshot so it does not enter downstream processing.
        drawer_removed = driver.execute_script("""
            const nodes = document.querySelectorAll('div.MuiDrawer-root');
            const count = nodes.length;
            nodes.forEach(n => n.remove());
            return count;
        """)
        if drawer_removed:
            print(f"Removed {drawer_removed} 'MuiDrawer-root' section(s) before snapshot.")

        # Let layout settle after DOM edits before capturing MHTML.
        time.sleep(1)

        mhtml_data = driver.execute_cdp_cmd("Page.captureSnapshot", {"format": "mhtml"})['data']

        filename = None
        try:
            msg = email.message_from_string(mhtml_data)
            for part in msg.walk():
                if part.get_content_type() == 'text/html':
                    content = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    soup = BeautifulSoup(content, 'html.parser')
                    
                    # Priority 1: Specific data-cy attribute (Course Title)
                    course_title_text = ""
                    course_title_node = soup.find(attrs={"data-cy": "course-title-input"})
                    if course_title_node:
                        # Check for input value if it's a form field (common in React/Mui)
                        input_node = course_title_node.find('input')
                        if input_node and input_node.get('value'):
                            course_title_text = input_node.get('value').strip()
                        else:
                            course_title_text = course_title_node.get_text(" ", strip=True)

                    title_text = soup.title.get_text(" ", strip=True) if soup.title else ""
                    h1_text = ""

                    # Iterate over all h1 tags to find the first meaningful one
                    for h1 in soup.find_all('h1'):
                        text = h1.get_text(" ", strip=True)
                        # Skip generic "Heading 1" from toolbars or empty headers
                        if text and text.lower() != "heading 1":
                            h1_text = text
                            break

                    # Determine final filename text (Priority: data-cy > H1 > Title)
                    if course_title_text:
                        final_text = course_title_text
                    elif h1_text:
                        final_text = h1_text
                    else:
                        final_text = title_text
                    
                    if final_text:
                        clean_name = re.sub(r'[^\w\-_.]', '_', final_text)[:150]
                        filename = f"{clean_name}.mhtml"
                        break
        except Exception as e:
            print(f"Warning: Could not extract H1 from MHTML: {e}")

        if not filename:
            filename = re.sub(r'[^\w\-_.]', '_', url) + '.mhtml'

        mhtml_path = output_dir / filename
        if mhtml_path.exists():
            print(f"Skipping save, file already exists: {filename}")
            return mhtml_path

        with open(mhtml_path, "w", encoding="utf-8", newline='') as f:
            f.write(mhtml_data)
        print(f"Successfully saved MHTML to {mhtml_path}")
        return mhtml_path
    except Exception as e:
        print(f"Error downloading URL {url}: {e}")
        return None
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass