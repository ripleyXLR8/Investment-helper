import os
import json
import logging
import datetime
from finary_uapi import auth, me, investments

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class FinaryClient:
    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.credentials_path = "credentials.json"
        
    def _prepare_credentials(self):
        """Creates the credentials.json file required by finary_uapi."""
        creds = {
            "email": self.email,
            "password": self.password
        }
        with open(self.credentials_path, "w") as f:
            json.dump(creds, f)
        logging.info("Credentials file prepared.")

    def login(self):
        """Handles authentication."""
        self._prepare_credentials()
        
        # Check if already authenticated via session file
        if not auth.is_authenticated():
            logging.info("Not authenticated. Attempting signin...")
            try:
                # This function usually reads from credentials.json
                auth.signin()
                logging.info("Signin successful.")
            except Exception as e:
                logging.error(f"Authentication failed: {e}")
                logging.error("If MFA is enabled, you might need to run 'python -m finary_uapi signin' manually once.")
                return False
        else:
            logging.info("Already authenticated via existing session.")
        return True

    def fetch_and_save(self, output_dir):
        """Fetches data and saves it to a JSON file."""
        if not self.login():
            return False

        try:
            logging.info("Fetching data from Finary...")
            data = {
                "timestamp": datetime.datetime.now().isoformat(),
                "me": me.get_me(),
                "investments": investments.get_investments()
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
