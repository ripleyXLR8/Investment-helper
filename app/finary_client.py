import os
import json
import logging
import datetime
from finary_uapi.signin import signin
from finary_uapi.auth import prepare_session
from finary_uapi.user_me import get_user_me
from finary_uapi.user_portfolio import get_portfolio_investments

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class FinaryClient:
    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.session = None
        
    def login(self):
        """Handles authentication and session preparation."""
        # finary_uapi reads FINARY_EMAIL and FINARY_PASSWORD from env
        os.environ["FINARY_EMAIL"] = self.email
        os.environ["FINARY_PASSWORD"] = self.password
        
        try:
            logging.info("Attempting signin...")
            # signin() handles credentials and creates necessary JWT/Cookie files
            signin()
            
            logging.info("Preparing session...")
            # prepare_session() loads the saved tokens and returns a session object
            self.session = prepare_session()
            logging.info("Session ready.")
            return True
        except Exception as e:
            logging.error(f"Authentication failed: {e}")
            return False

    def fetch_and_save(self, output_dir):
        """Fetches data and saves it to a JSON file."""
        if not self.login():
            return False

        try:
            logging.info("Fetching data from Finary...")
            
            # Fetch data using the session
            me_data = get_user_me(self.session)
            portfolio_data = get_portfolio_investments(self.session)
            
            data = {
                "timestamp": datetime.datetime.now().isoformat(),
                "me": me_data,
                "portfolio": portfolio_data
            }
            
            # Ensure output directory exists
            os.makedirs(output_dir, exist_ok=True)
            
            filename = f"finary_data_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = os.path.join(output_dir, filename)
            
            with open(filepath, "w", encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            
            logging.info(f"Data successfully saved to {filepath}")
            return True
        except Exception as e:
            logging.error(f"Error fetching data: {e}")
            return False
