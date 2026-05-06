import os
import time
import schedule
import logging
from dotenv import load_dotenv
from finary_client import FinaryClient

# Load environment variables
load_dotenv()

FINARY_EMAIL = os.getenv("FINARY_EMAIL")
FINARY_PASSWORD = os.getenv("FINARY_PASSWORD")
FINARY_OTP_SECRET = os.getenv("FINARY_OTP_SECRET")
DATA_DIR = os.getenv("DATA_DIR", "/app/data")
SCHEDULE_TIME = os.getenv("SCHEDULE_TIME", "03:00")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def job():
    logging.info("Starting daily Finary data download...")
    if not FINARY_EMAIL or not FINARY_PASSWORD:
        logging.error("FINARY_EMAIL or FINARY_PASSWORD environment variables are missing!")
        return

    client = FinaryClient(FINARY_EMAIL, FINARY_PASSWORD, FINARY_OTP_SECRET)
    client.fetch_and_save(DATA_DIR)

def main():
    logging.info(f"Finary Downloader started. Job scheduled daily at {SCHEDULE_TIME}")
    
    # Run once immediately on start
    job()

    # Schedule the job
    schedule.every().day.at(SCHEDULE_TIME).do(job)

    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    main()
