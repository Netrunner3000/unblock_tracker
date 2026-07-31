#!/bin/bash

while true
do
    echo "🔁 Starting unblock monitor script..."
    python3 sniper_hardened_login_verified.py
    echo "⚠️ Script exited at $(date). Restarting in 30 seconds..."
    sleep 30
done
