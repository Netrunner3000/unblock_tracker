
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import NoSuchElementException
import time
from datetime import datetime
import requests

from env_config import env

# --- CONFIGURATION ---
INSTAGRAM_USERNAME = env("INSTAGRAM_USERNAME", required=True)
INSTAGRAM_PASSWORD = env("INSTAGRAM_PASSWORD", required=True)
TARGET_PROFILE = env("TARGET_PROFILE", required=True)
CHROME_DRIVER_PATH = '/opt/homebrew/bin/chromedriver'
CHECK_INTERVAL = 60  # every 60 seconds
LOG_FILE = 'selenium_ig_log_test.txt'

# --- TELEGRAM CONFIG ---
TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN", required=True)
TELEGRAM_CHAT_ID = env("TELEGRAM_CHAT_ID", required=True)

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

# --- BROWSER SETUP ---
options = Options()
options.binary_location = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
options.add_argument("--headless")
options.add_argument("--disable-gpu")
options.add_argument("--window-size=1920,1080")

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

def monitor():
    service = Service(CHROME_DRIVER_PATH)
    driver = webdriver.Chrome(service=service, options=options)
    login(driver)

    last_status = None
    while True:
        status = check_block_status(driver)
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{now}] Status: {status}"
        print(log_entry)

        with open(LOG_FILE, 'a') as f:
            f.write(log_entry + "\n")

        if status != last_status and "Unblocked" in status:
            print(f">>> UNBLOCK DETECTED at {now}")
            send_telegram_message(f"📱 You have been UNBLOCKED by @{TARGET_PROFILE} at {now}")
        last_status = status

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    monitor()
