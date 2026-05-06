import os
import json
import logging
import datetime
import pyotp
from finary_uapi.signin import signin
from finary_uapi.auth import prepare_session
from finary_uapi.user_me import get_user_me, get_user_me_organizations
from finary_uapi.user_portfolio import get_portfolio
from finary_uapi.user_organizations import (
    get_organization_investments,
    get_organization_cryptos,
    get_organization_fonds_euro,
    get_organization_scpis,
    get_organization_real_estates
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class FinaryClient:
    def __init__(self, email, password, otp_secret=None):
        self.email = email
        self.password = password
        self.otp_secret = otp_secret
        self.session = None
        
    def login(self):
        os.environ["FINARY_EMAIL"] = self.email
        os.environ["FINARY_PASSWORD"] = self.password
        otp_code = ""
        if self.otp_secret:
            try:
                totp = pyotp.TOTP(self.otp_secret.replace(" ", ""))
                otp_code = totp.now()
            except Exception as e:
                logging.error(f"Failed to generate OTP code: {e}")

        try:
            signin(otp_code=otp_code)
            self.session = prepare_session()
            return True
        except Exception as e:
            logging.error(f"Authentication failed: {e}")
            return False

    def fetch_and_save(self, output_dir):
        if not self.login():
            return False

        try:
            logging.info("Fetching ALL organizations and data...")
            me_data = get_user_me(self.session)
            orgs_response = get_user_me_organizations(self.session)
            organizations = orgs_response.get("result", [])
            
            # Start with personal view
            all_assets = {
                "investments": [],
                "cryptos": [],
                "fonds_euro": [],
                "scpis": [],
                "real_estates": []
            }
            total_wealth = 0

            # 1. Fetch Personal Assets
            logging.info("Fetching Personal assets...")
            for cat in all_assets.keys():
                try:
                    data = get_portfolio(self.session, cat).get("result", {})
                    all_assets[cat].extend(self._extract_items(cat, data))
                    total_wealth += data.get("total", {}).get("amount", 0)
                except: pass

            # 2. Fetch Assets for each Organization (Family, Business, etc.)
            for org in organizations:
                org_id = org.get("id")
                org_name = org.get("name")
                logging.info(f"Fetching assets for organization: {org_name} ({org_id})...")
                
                # Mapping functions
                org_funcs = {
                    "investments": get_organization_investments,
                    "cryptos": get_organization_cryptos,
                    "fonds_euro": get_organization_fonds_euro,
                    "scpis": get_organization_scpis,
                    "real_estates": get_organization_real_estates
                }
                
                for cat, func in org_funcs.items():
                    try:
                        data = func(self.session, org_id).get("result", {})
                        items = self._extract_items(cat, data)
                        # Avoid duplicates if Finary repeats items in different views
                        all_assets[cat].extend(items)
                        total_wealth += data.get("total", {}).get("amount", 0)
                    except Exception as e:
                        logging.warning(f"Error fetching {cat} for org {org_name}: {e}")

            data = {
                "timestamp": datetime.datetime.now().isoformat(),
                "me": me_data,
                "organizations": organizations,
                "portfolio_summary": {
                    "total_amount": total_wealth,
                    "categories": all_assets
                }
            }
            
            os.makedirs(output_dir, exist_ok=True)
            filename = f"finary_data_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = os.path.join(output_dir, filename)
            with open(filepath, "w", encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            
            logging.info(f"Consolidated data saved to {filepath}")
            return True
        except Exception as e:
            logging.error(f"Error: {e}")
            return False

    def _extract_items(self, category, data):
        """Helper to extract the actual list of items from Finary response."""
        if category == "investments": return data.get("accounts", [])
        if category == "cryptos": return data.get("cryptos", [])
        if category == "fonds_euro": return data.get("fonds_euro", [])
        if category == "scpis": return data.get("scpis", [])
        if category == "real_estates": return data.get("real_estates", [])
        return []
