import os
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

NOJUICE_URL = os.getenv("NOJUICE_URL", "https://www.nojuice.ag")
USERNAME = os.getenv("NOJUICE_USERNAME")
PASSWORD = os.getenv("NOJUICE_PASSWORD")

if not USERNAME or not PASSWORD:
    raise RuntimeError("Missing NOJUICE_USERNAME / NOJUICE_PASSWORD")

print("Starting debug login flow...")
print("Browser will stay open until you press ENTER.")

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=False,
        slow_mo=800  # 👈 slows *every* action so you can see it
    )

    context = browser.new_context()
    page = context.new_page()

    print("Navigating to site...")
    page.goto(NOJUICE_URL)
    input("Loaded login page. Press ENTER to continue...")

    print("Filling username...")
    page.fill('input[name="customerID"]', USERNAME)
    input("Username filled. Press ENTER to continue...")

    print("Filling password...")
    page.fill('input[name="Password"]', PASSWORD)
    input("Password filled. Press ENTER to continue...")

    print("Clicking LOGIN...")
    page.click('button[data-action="login"]')
    input("Clicked LOGIN. Watch the page. Press ENTER to continue...")

    print("Waiting 10 seconds for any JS / Cloudflare / redirects...")
    page.wait_for_timeout(10000)

    print("Current URL:", page.url)
    print("Saving screenshot + HTML...")

    page.screenshot(path="debug_after_login.png", full_page=True)
    with open("debug_after_login.html", "w", encoding="utf-8") as f:
        f.write(page.content())

    print("Artifacts written:")
    print("  - debug_after_login.png")
    print("  - debug_after_login.html")

    input("Press ENTER to close the browser...")
    browser.close()
