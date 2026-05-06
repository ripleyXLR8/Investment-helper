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

# No basicConfig here, it's handled by main.py

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
            organizations = orgs_response.get("result", []) if isinstance(orgs_response, dict) else orgs_response
            
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
                    res = get_portfolio(self.session, cat)
                    data = res.get("result", {}) if isinstance(res, dict) else {}
                    items = self._extract_items(cat, data)
                    all_assets[cat].extend(items)
                    total_wealth += data.get("total", {}).get("amount", 0) if isinstance(data, dict) else 0
                except Exception as e:
                    logging.debug(f"Skipping personal {cat}: {e}")

            # 2. Fetch Assets for each Organization
            for org in organizations:
                if not isinstance(org, dict): continue
                org_id = org.get("id")
                org_name = org.get("name")
                logging.info(f"Fetching assets for organization: {org_name} ({org_id})...")
                
                org_funcs = {
                    "investments": get_organization_investments,
                    "cryptos": get_organization_cryptos,
                    "fonds_euro": get_organization_fonds_euro,
                    "scpis": get_organization_scpis,
                    "real_estates": get_organization_real_estates
                }
                
                for cat, func in org_funcs.items():
                    try:
                        res = func(self.session, org_id)
                        if isinstance(res, list):
                            items = res
                            for item in items:
                                total_wealth += item.get("balance", 0) if isinstance(item, dict) else 0
                        elif isinstance(res, dict):
                            data = res.get("result", res)
                            items = self._extract_items(cat, data)
                            total_wealth += data.get("total", {}).get("amount", 0) if isinstance(data, dict) and "total" in data else 0
                        else:
                            items = []
                        
                        all_assets[cat].extend(items)
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
            logging.error(f"Global Error: {e}")
            return False

    def _extract_items(self, category, data):
        if not isinstance(data, dict): return []
        if category == "investments": return data.get("accounts", [])
        if category == "cryptos": return data.get("cryptos", [])
        if category == "fonds_euro": return data.get("fonds_euro", [])
        if category == "scpis": return data.get("scpis", [])
        if category == "real_estates": return data.get("real_estates", [])
        return []
