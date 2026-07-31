
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import NoSuchElementException
import time
from datetime import datetime, timedelta
import requests
import random
import csv
import os

from env_config import env

# --- CONFIGURATION ---
INSTAGRAM_USERNAME = env("INSTAGRAM_USERNAME", required=True)
INSTAGRAM_PASSWORD = env("INSTAGRAM_PASSWORD", required=True)
TARGET_PROFILE = env("TARGET_PROFILE", required=True)
CHROME_DRIVER_PATH = '/opt/homebrew/bin/chromedriver'
LOG_FILE = 'selenium_ig_test_log.txt'
CSV_FILE = 'unblock_events_test.csv'
SCREENSHOT_DIR = 'screenshots_test'
MAX_RUNTIME_SECONDS = 7200  # 2 hours max test session
CYCLE_LIMIT = 100  # Restart browser every 100 checks

# --- TELEGRAM CONFIG ---
TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN", required=True)
TELEGRAM_CHAT_ID = env("TELEGRAM_CHAT_ID", required=True)

# --- USER-AGENTS LIST ---
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.5993.117 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Gecko/20100101 Firefox/115.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Brave/1.52.129 Chrome/113.0.0.0 Safari/537.36"
]

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }
    try:
        requests.post(url, data=data)
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")

def get_options():
    options = Options()
    options.binary_location = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    # Set random user-agent
    ua = random.choice(USER_AGENTS)
    options.add_argument(f"user-agent={ua}")

    # Optional: Add proxy for IP rotation
    # options.add_argument("--proxy-server=http://YOUR_PROXY_IP:PORT")

    return options

def login(driver):
    driver.get("https://www.instagram.com/accounts/login/")
    time.sleep(3)
    username_input = driver.find_element(By.NAME, "username")
    password_input = driver.find_element(By.NAME, "password")
    username_input.send_keys(INSTAGRAM_USERNAME)
    password_input.send_keys(INSTAGRAM_PASSWORD)
    password_input.send_keys(Keys.RETURN)
    time.sleep(5)

def check_block_status(driver):
    profile_url = f"https://www.instagram.com/{TARGET_PROFILE}/"
    driver.get(profile_url)
    time.sleep(5)
    page_source = driver.page_source

    if "Sorry, this page isn't available." in page_source or "The link you followed may be broken" in page_source:
        return "Blocked or Profile Not Found"
    try:
        driver.find_element(By.XPATH, "//h2[text()='This Account is Private']")
        return "Unblocked (Private)"
    except NoSuchElementException:
        pass
    try:
        driver.find_element(By.XPATH, "//h1[contains(text(), 'Page Not Found')]")
        return "Blocked"
    except NoSuchElementException:
        pass

    return "Unblocked (Public or Cached)"

def save_csv_entry(timestamp, status):
    file_exists = os.path.isfile(CSV_FILE)
    with open(CSV_FILE, 'a', newline='') as csvfile:
        writer = csv.writer(csvfile)
        if not file_exists:
            writer.writerow(["Timestamp", "Status"])
        writer.writerow([timestamp, status])

def capture_screenshot(driver, filename):
    if not os.path.exists(SCREENSHOT_DIR):
        os.makedirs(SCREENSHOT_DIR)
    driver.save_screenshot(os.path.join(SCREENSHOT_DIR, filename))

def start_browser():
    options = get_options()
    service = Service(CHROME_DRIVER_PATH)
    driver = webdriver.Chrome(service=service, options=options)
    login(driver)
    return driver

def monitor():
    print("🚀 Starting Instagram unblock monitor (Enhanced Mode)...")
    start_time = datetime.now()
    last_status = None
    cycles = 0
    driver = start_browser()

    while True:
        now = datetime.now()
        current_hour = now.hour

        # Sleep between 2 AM and 6 AM
        if 2 <= current_hour < 6:
            print("🌙 Night break: sleeping until 06:00...")
            time.sleep((6 - current_hour) * 3600)
            continue

        status = check_block_status(driver)
        timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{timestamp}] Status: {status}"
        print(log_entry)

        with open(LOG_FILE, 'a') as f:
            f.write(log_entry + "\n")

        if status != last_status and "Unblocked" in status:
            screenshot_name = f"{now.strftime('%Y%m%d_%H%M%S')}_unblocked.png"
            capture_screenshot(driver, screenshot_name)
            save_csv_entry(timestamp, status)
            print(f">>> UNBLOCK DETECTED at {timestamp}")
            send_telegram_message(f"📸 UNBLOCKED by @{TARGET_PROFILE} at {timestamp}. Screenshot saved.")
            break

        last_status = status

        if (now - start_time).total_seconds() > MAX_RUNTIME_SECONDS:
            print("⏱️ Max runtime reached. Exiting...")
            break

        cycles += 1
        if cycles >= CYCLE_LIMIT:
            print("🔁 Restarting browser to reduce detection risk...")
            driver.quit()
            driver = start_browser()
            cycles = 0

        wait_time = random.randint(10, 20)
        print(f"⏳ Waiting {wait_time} seconds before next check...")
        time.sleep(wait_time)

    driver.quit()

if __name__ == "__main__":
    monitor()
