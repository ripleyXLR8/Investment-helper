import os
import json
import logging
import datetime
import pyotp
from finary_uapi.signin import signin
from finary_uapi.auth import prepare_session
from finary_uapi.user_me import get_user_me
from finary_uapi.user_portfolio import get_portfolio

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class FinaryClient:
    def __init__(self, email, password, otp_secret=None):
        self.email = email
        self.password = password
        self.otp_secret = otp_secret
        self.session = None
        
    def login(self):
        """Handles authentication and session preparation."""
        os.environ["FINARY_EMAIL"] = self.email
        os.environ["FINARY_PASSWORD"] = self.password
        
        otp_code = ""
        if self.otp_secret:
            try:
                totp = pyotp.TOTP(self.otp_secret.replace(" ", ""))
                otp_code = totp.now()
                logging.info("OTP code generated automatically.")
            except Exception as e:
                logging.error(f"Failed to generate OTP code: {e}")

        try:
            logging.info("Attempting signin...")
            signin(otp_code=otp_code)
            
            logging.info("Preparing session...")
            self.session = prepare_session()
            logging.info("Session ready.")
            return True
        except Exception as e:
            logging.error(f"Authentication failed: {e}")
            return False

    def fetch_and_save(self, output_dir):
        """Fetches ALL data categories and saves them to a JSON file."""
        if not self.login():
            return False

        try:
            logging.info("Fetching ALL data from Finary...")
            
            # Fetch User Profile
            me_data = get_user_me(self.session)
            
            # Categories to fetch
            categories = [
                "investments", 
                "cryptos", 
                "fonds_euro", 
                "scpis", 
                "real_estates", 
                "precious_metals",
                "crowdlendings"
            ]
            
            portfolio_all = {}
            total_wealth = 0
            
            for cat in categories:
                try:
                    logging.info(f"Fetching category: {cat}...")
                    cat_data = get_portfolio(self.session, cat)
                    portfolio_all[cat] = cat_data.get("result", {})
                    # Accumulate total from each category if available
                    total_wealth += cat_data.get("result", {}).get("total", {}).get("amount", 0)
                except Exception as e:
                    logging.warning(f"Could not fetch {cat}: {e}")

            data = {
                "timestamp": datetime.datetime.now().isoformat(),
                "me": me_data,
                "portfolio_summary": {
                    "total_amount": total_wealth,
                    "categories": portfolio_all
                }
            }
            
            os.makedirs(output_dir, exist_ok=True)
            filename = f"finary_data_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = os.path.join(output_dir, filename)
            
            with open(filepath, "w", encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            
            logging.info(f"Full data successfully saved to {filepath}")
            return True
        except Exception as e:
            logging.error(f"Error fetching data: {e}")
            return False
