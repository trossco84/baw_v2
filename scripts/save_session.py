import os
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

load_dotenv()

URL = os.getenv("NOJUICE_URL", "https://www.nojuice.ag")
USER = os.getenv("NOJUICE_USERNAME")
PW = os.getenv("NOJUICE_PASSWORD")

if not USER or not PW:
    raise RuntimeError("Missing NOJUICE_USERNAME / NOJUICE_PASSWORD")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()

    page.goto(URL, wait_until="domcontentloaded")
    page.fill('input[name="customerID"]', USER)
    page.fill('input[name="Password"]', PW)
    page.click('button[data-action="login"]')

    # Wait for login page to disappear OR for an authenticated UI element to appear
    try:
        page.wait_for_selector('input[name="customerID"]', state="detached", timeout=60000)
    except PWTimeoutError:
        pass

    # Now wait for something that only exists when logged in
    # (Weekly Figures is fine here because you’re watching it work)
    page.wait_for_selector("text=Weekly Figures", timeout=60000)

    # Optional: click into Weekly Figures to force token creation
    page.click("text=Weekly Figures")
    page.wait_for_timeout(2000)

    context.storage_state(path="storage_state.json")
    print("Saved storage_state.json")
    browser.close()
