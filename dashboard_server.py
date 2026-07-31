# dashboard_server.py
from flask import Flask, render_template, send_from_directory
import csv
import os
from datetime import datetime

app = Flask(__name__)

CSV_FILE = 'unblock_events_safe_login.csv'
SCREENSHOT_DIR = 'screenshots_safe_login'

@app.route('/')
def dashboard():
    entries = []
    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                timestamp = row['Timestamp']
                status = row['Status']
                img_filename = f"{timestamp.replace(':', '').replace('-', '').replace(' ', '_')}_unblocked.png"
                img_path = os.path.join(SCREENSHOT_DIR, img_filename)
                if os.path.exists(img_path):
                    img_url = f"/screenshot/{img_filename}"
                else:
                    img_url = None
                entries.append({'timestamp': timestamp, 'status': status, 'img_url': img_url})
    return render_template('dashboard.html', entries=entries[::-1])

@app.route('/screenshot/<filename>')
def serve_screenshot(filename):
    return send_from_directory(SCREENSHOT_DIR, filename)

if __name__ == '__main__':
    app.run(debug=True, port=5000)