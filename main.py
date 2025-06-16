import time
import json
import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

load_dotenv()

# === CONFIGURATION ===
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
DATA_FILE = "lowest_prices.json"
CHECK_INTERVAL = 60  # seconds
URL = "https://www.skyscanner.net/transport/flights/lond/tbs?adultsv2=1&cabinclass=economy&childrenv2=&inboundaltsenabled=false&iym=2508&outboundaltsenabled=false&oym=2507&preferdirects=true&rtn=1&selectedoday=01&selectediday=01"

# === EMAIL NOTIFICATION ===
def send_email_notification(price_changes):
    subject = f"{len(price_changes)} New Low Price(s) Found!"
    lines = []
    for date, new_price, old_price in price_changes:
        lines.append(f"{date}: £{new_price} (was £{old_price if old_price is not None else 'N/A'})")
    body = "\n".join(lines) + f"\n\nView on Skyscanner:\n{URL}"

    msg = EmailMessage()
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = EMAIL_ADDRESS
    msg['Subject'] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            smtp.send_message(msg)
        print(f"[EMAIL SENT] {subject}")
    except Exception as e:
        print(f"[EMAIL FAILED] {e}")

# === FILE STORAGE ===
def load_local_prices():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_local_prices(prices):
    with open(DATA_FILE, "w") as f:
        json.dump(prices, f, indent=2)

# === COOKIE + CHECKBOX ===
def accept_cookies(driver):
    try:
        accept_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(),'Accept')]"))
        )
        accept_button.click()
        print("Cookies accepted.")
    except TimeoutException:
        print("No cookie banner or already accepted.")

def check_direct_flights_checkbox(driver):
    try:
        # Wait for the checkbox to be present and clickable
        checkbox = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "input.BpkCheckbox_bpk-checkbox__input__M2ZjN[data-testid='prefer-directs']"))
        )
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", checkbox)
        time.sleep(0.5)  # Small delay to ensure visibility

        if not checkbox.is_selected():
            checkbox.click()
            print("Checked 'Direct flights' checkbox.")
        else:
            print("'Direct flights' already checked.")
    except Exception as e:
        print("Failed to check 'Direct flights' checkbox:", e)

# === PRICE SCRAPER ===
def scrape_prices(driver):
    prices = {}
    try:
        WebDriverWait(driver, 60).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.BpkCalendarWeek_bpk-calendar-week__MGQ2N"))
        )
    except TimeoutException:
        print("Timed out waiting for calendar to load.")
        return prices

    week_rows = driver.find_elements(By.CSS_SELECTOR, "div.BpkCalendarWeek_bpk-calendar-week__MGQ2N")

    for week in week_rows:
        day_buttons = week.find_elements(By.CSS_SELECTOR, "button.month-view-calendar__cell")
        for btn in day_buttons:
            date = btn.get_attribute("aria-label")
            try:
                price_elem = btn.find_element(By.CSS_SELECTOR, "p.price")
                price_text = price_elem.text.strip()
                price = int(price_text.replace("£", ""))
            except:
                price = None
            if date:
                parts = date.split(",")
                if len(parts) > 1:
                    date_clean = parts[1].strip()  # "01 July 2025"
                else:
                    date_clean = date.strip()
                prices[date_clean] = price

    return prices

# === MAIN LOOP ===
def main():
    lowest_prices = load_local_prices()
    print("Loaded previous lowest prices from disk.")

    options = uc.ChromeOptions()
    options.add_argument("--window-size=1920,1080")
    # options.add_argument("--headless")  # Uncomment if you want headless mode

    driver = uc.Chrome(options=options)
    driver.get(URL)

    accept_cookies(driver)
    input(">> Solve CAPTCHA if present, then press Enter to continue...")

    while True:
        check_direct_flights_checkbox(driver)
        current_prices = scrape_prices(driver)

        new_low_prices = []

        for date, price in current_prices.items():
            if price is not None:
                old_price = lowest_prices.get(date)
                if old_price is None or price < old_price:
                    print(f"[NEW LOW] {date}: £{price} (was £{old_price})")
                    new_low_prices.append((date, price, old_price))
                    lowest_prices[date] = price

        if new_low_prices:
            send_email_notification(new_low_prices)
            save_local_prices(lowest_prices)
            print("Saved updated prices to disk.")

        print(f"Waiting {CHECK_INTERVAL} seconds...\n")
        time.sleep(CHECK_INTERVAL)
        driver.get(URL)

if __name__ == "__main__":
    main()
