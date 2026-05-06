import os
import time
import schedule
import logging
import signal
import sys
import threading
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

FINARY_EMAIL = os.getenv("FINARY_EMAIL")
FINARY_PASSWORD = os.getenv("FINARY_PASSWORD")
FINARY_OTP_SECRET = os.getenv("FINARY_OTP_SECRET")
SCHEDULE_TIME = os.getenv("SCHEDULE_TIME", "03:00")
DATA_DIR = os.getenv("DATA_DIR", "/app/data")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Ensure data dir exists
os.makedirs(DATA_DIR, exist_ok=True)
log_file = os.path.join(DATA_DIR, "app.log")

# Configure Logging (Force clean start)
root_logger = logging.getLogger()
if root_logger.hasHandlers():
    root_logger.handlers.clear()

file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

root_logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
root_logger.addHandler(file_handler)
root_logger.addHandler(stream_handler)

# IMPORTANT: Test log to confirm file is working
logging.info(f"--- Finary Downloader Startup (Level: {LOG_LEVEL}) ---")

# Import after logging setup
from finary_client import FinaryClient
from server import app as flask_app

def heartbeat():
    with open("/tmp/heartbeat", "w") as f:
        f.write(str(time.time()))

def job():
    logging.info("Starting scheduled Finary data download...")
    client = FinaryClient(FINARY_EMAIL, FINARY_PASSWORD, FINARY_OTP_SECRET)
    if client.fetch_and_save(DATA_DIR):
        logging.info("Download completed successfully.")
    else:
        logging.error("Download failed.")
    file_handler.flush() # Force write to disk

def run_scheduler():
    schedule.every().day.at(SCHEDULE_TIME).do(job)
    logging.info(f"Scheduler initialized for {SCHEDULE_TIME}")
    
    # Run once at startup
    job()
    
    while True:
        schedule.run_pending()
        heartbeat()
        time.sleep(60)

def signal_handler(sig, frame):
    logging.info("Shutting down gracefully...")
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    logging.info("Starting Flask dashboard...")
    flask_thread = threading.Thread(target=lambda: flask_app.run(host="0.0.0.0", port=5000, use_reloader=False))
    flask_thread.daemon = True
    flask_thread.start()

    run_scheduler()
