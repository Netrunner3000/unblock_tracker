
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import NoSuchElementException, WebDriverException
import time
from datetime import datetime
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
LOG_FILE = 'ig_log_auto_proxy.txt'
CSV_FILE = 'unblock_events_auto_proxy.csv'
SCREENSHOT_DIR = 'screenshots_auto_proxy'
MAX_RUNTIME_SECONDS = 7200
CYCLE_LIMIT = 100

# --- TELEGRAM CONFIG ---
TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN", required=True)
TELEGRAM_CHAT_ID = env("TELEGRAM_CHAT_ID", required=True)

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.5993.117 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Gecko/20100101 Firefox/115.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Brave/1.52.129 Chrome/113.0.0.0 Safari/537.36"
]

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, data=data)
    except Exception as e:
        print(f"Telegram error: {e}")

def fetch_proxies():
    print("🌐 Fetching fresh proxy list...")
    try:
        res = requests.get("https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=3000&country=all")
        proxy_list = res.text.strip().split("\n")
        print(f"✅ {len(proxy_list)} proxies fetched.")
        return proxy_list
    except Exception as e:
        print(f"❌ Failed to fetch proxies: {e}")
        return []

def validate_proxy(proxy):
    try:
        res = requests.get("http://httpbin.org/ip", proxies={"http": proxy, "https": proxy}, timeout=5)
        return res.status_code == 200
    except:
        return False

def get_working_proxy(proxy_pool):
    print("🔍 Searching for working proxy...")
    random.shuffle(proxy_pool)
    for proxy in proxy_pool:
        if validate_proxy(proxy):
            print(f"✅ Valid proxy: {proxy}")
            return proxy
    print("❌ No working proxies found.")
    return None

def get_options(proxy):
    options = Options()
    options.binary_location = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    ua = random.choice(USER_AGENTS)
    options.add_argument(f"user-agent={ua}")
    if proxy:
        options.add_argument(f"--proxy-server={proxy}")
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
    driver.get(f"https://www.instagram.com/{TARGET_PROFILE}/")
    time.sleep(5)
    page = driver.page_source
    if "Sorry, this page isn't available." in page or "The link you followed may be broken" in page:
        return "Blocked or Profile Not Found"
    try:
        driver.find_element(By.XPATH, "//h2[text()='This Account is Private']")
        return "Unblocked (Private)"
    except NoSuchElementException:
        pass
    return "Unblocked (Public or Cached)"

def save_csv_entry(timestamp, status):
    file_exists = os.path.isfile(CSV_FILE)
    with open(CSV_FILE, 'a', newline='') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Timestamp", "Status"])
        writer.writerow([timestamp, status])

def capture_screenshot(driver, filename):
    if not os.path.exists(SCREENSHOT_DIR):
        os.makedirs(SCREENSHOT_DIR)
    driver.save_screenshot(os.path.join(SCREENSHOT_DIR, filename))

def start_browser(proxy):
    options = get_options(proxy)
    service = Service(CHROME_DRIVER_PATH)
    driver = webdriver.Chrome(service=service, options=options)
    login(driver)
    return driver

def monitor():
    print("🚀 Starting smart sniper with automatic proxy fetch + validation")
    start_time = datetime.now()
    last_status = None
    cycles = 0
    proxy_pool = fetch_proxies()
    current_proxy = get_working_proxy(proxy_pool)
    driver = start_browser(current_proxy)

    while True:
        now = datetime.now()
        if 2 <= now.hour < 6:
            print("🌙 Sleeping during night break...")
            time.sleep((6 - now.hour) * 3600)
            continue

        try:
            status = check_block_status(driver)
        except WebDriverException as e:
            print(f"💥 Browser error: {e}. Restarting...")
            driver.quit()
            current_proxy = get_working_proxy(proxy_pool)
            driver = start_browser(current_proxy)
            continue

        timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] Status: {status}")

        with open(LOG_FILE, 'a') as f:
            f.write(f"[{timestamp}] Status: {status}\n")

        if status != last_status and "Unblocked" in status:
            screenshot = f"{now.strftime('%Y%m%d_%H%M%S')}_unblocked.png"
            capture_screenshot(driver, screenshot)
            save_csv_entry(timestamp, status)
            send_telegram_message(f"📸 UNBLOCKED by @{TARGET_PROFILE} at {timestamp}. Screenshot saved.")
            break

        last_status = status

        if (now - start_time).total_seconds() > MAX_RUNTIME_SECONDS:
            print("⏱️ Time limit reached. Exiting.")
            break

        cycles += 1
        if cycles >= CYCLE_LIMIT:
            print("🔁 Restarting browser to rotate proxy + fingerprint...")
            driver.quit()
            current_proxy = get_working_proxy(proxy_pool)
            driver = start_browser(current_proxy)
            cycles = 0

        wait_time = random.randint(10, 20)
        print(f"⏳ Waiting {wait_time} seconds...")
        time.sleep(wait_time)

    driver.quit()

if __name__ == "__main__":
    monitor()
