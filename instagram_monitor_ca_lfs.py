
from pushbullet import Pushbullet
import requests
from bs4 import BeautifulSoup
import hashlib
import time
from datetime import datetime

from env_config import env

# CONFIG
TARGET_USERNAME = env("TARGET_PROFILE", required=True)
CHECK_INTERVAL = 60  # in seconds
PUSHBULLET_TOKEN = env("PUSHBULLET_TOKEN", required=True)

pb = Pushbullet(PUSHBULLET_TOKEN)

def hash_image(image_url):
    try:
        img_data = requests.get(image_url, timeout=10).content
        return hashlib.md5(img_data).hexdigest()
    except:
        return None

def check_instagram_profile(username):
    url = f"https://www.instagram.com/{username}/"
    headers = {
        'User-Agent': 'Mozilla/5.0',
    }

    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 404 or 'Sorry, this page isn’t available.' in r.text:
            return 'Blocked or Deactivated', None

        soup = BeautifulSoup(r.text, 'html.parser')
        og_image = soup.find('meta', property='og:image')
        if og_image:
            image_url = og_image['content']
            img_hash = hash_image(image_url)
            return 'Visible', img_hash
        else:
            return 'Blocked or No Picture', None

    except Exception as e:
        return f'Error: {e}', None

def monitor():
    last_status = None
    last_hash = None

    while True:
        status, img_hash = check_instagram_profile(TARGET_USERNAME)
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if status != last_status or img_hash != last_hash:
            print(f"[{now}] Change detected!")
            print(f"Status: {status}")
            print(f"Image Hash: {img_hash}")

            with open('log.txt', 'a') as f:
                f.write(f"[{now}] Status: {status}, Image Hash: {img_hash}\n")

            if status == 'Visible':
                pb.push_note("IG Monitor", f"{TARGET_USERNAME} may have unblocked you at {now}!")

            last_status = status
            last_hash = img_hash
        else:
            print(f"[{now}] No change. Status: {status}")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    monitor()
