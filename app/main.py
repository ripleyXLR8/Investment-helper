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
SCHEDULE_TIME = os.getenv("SCHEDULE_TIME", "03:00")
DATA_DIR = os.getenv("DATA_DIR", "/app/data")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Configure Logging (Console + File)
os.makedirs(DATA_DIR, exist_ok=True)
log_file = os.path.join(DATA_DIR, "app.log")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, mode='a', encoding='utf-8')
    ]
)

def heartbeat():
    """Updates a heartbeat file for Docker healthcheck."""
    with open("/tmp/heartbeat", "w") as f:
        f.write(str(time.time()))

def job():
    logging.info("Starting scheduled Finary data download...")
    client = FinaryClient(FINARY_EMAIL, FINARY_PASSWORD, FINARY_OTP_SECRET)
    if client.fetch_and_save(DATA_DIR):
        logging.info("Scheduled download completed successfully.")
    else:
        logging.error("Scheduled download failed.")

def run_scheduler():
    schedule.every().day.at(SCHEDULE_TIME).do(job)
    logging.info(f"Finary Downloader started. Job scheduled daily at {SCHEDULE_TIME} (Level: {LOG_LEVEL})")
    
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

    # Start Flask in a background thread
    logging.info("Starting Flask dashboard on port 5000...")
    flask_thread = threading.Thread(target=lambda: flask_app.run(host="0.0.0.0", port=5000, use_reloader=False))
    flask_thread.daemon = True
    flask_thread.start()

    # Start Scheduler in main thread
    run_scheduler()
