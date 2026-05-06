import os
import time
import schedule
import logging
import signal
import sys
import threading
from dotenv import load_dotenv
from finary_client import FinaryClient
from server import app as flask_app

# Load environment variables
load_dotenv()

FINARY_EMAIL = os.getenv("FINARY_EMAIL")
FINARY_PASSWORD = os.getenv("FINARY_PASSWORD")
FINARY_OTP_SECRET = os.getenv("FINARY_OTP_SECRET")
DATA_DIR = os.getenv("DATA_DIR", "/app/data")
SCHEDULE_TIME = os.getenv("SCHEDULE_TIME", "03:00")
HEARTBEAT_FILE = "/tmp/heartbeat"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def signal_handler(sig, frame):
    logging.info("Shutdown signal received. Exiting gracefully...")
    sys.exit(0)

# Register signals for clean exit
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def update_heartbeat():
    """Updates a heartbeat file to indicate the process is alive."""
    try:
        with open(HEARTBEAT_FILE, "w") as f:
            f.write(str(time.time()))
    except Exception as e:
        logging.error(f"Failed to update heartbeat: {e}")

def job():
    logging.info("Starting daily Finary data download...")
    if not FINARY_EMAIL or not FINARY_PASSWORD:
        logging.error("FINARY_EMAIL or FINARY_PASSWORD environment variables are missing!")
        return

    client = FinaryClient(FINARY_EMAIL, FINARY_PASSWORD, FINARY_OTP_SECRET)
    client.fetch_and_save(DATA_DIR)
    update_heartbeat()

def run_flask():
    """Run the Flask server."""
    logging.info("Starting Flask dashboard on port 5000...")
    flask_app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)

def main():
    logging.info(f"Finary Downloader started. Job scheduled daily at {SCHEDULE_TIME}")
    
    # Start Flask server in a separate thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Initial heartbeat
    update_heartbeat()
    
    # Run once immediately on start
    job()

    # Schedule the job
    schedule.every().day.at(SCHEDULE_TIME).do(job)

    while True:
        schedule.run_pending()
        update_heartbeat()
        time.sleep(30)

if __name__ == "__main__":
    main()
