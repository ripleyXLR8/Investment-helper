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
            logging.debug("Sign in successful!")
            return True
        except Exception as e:
            logging.error(f"Authentication failed: {e}")
            return False

    def _get_item_value(self, item):
        """Helper to extract value from any type of Finary asset."""
        if not isinstance(item, dict): return 0
        return (
            item.get("balance") or 
            item.get("current_value") or 
            item.get("current_price") or 
            item.get("buying_price") or 0
        )

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
                    
                    # Calculate total from items if summary is missing
                    cat_total = data.get("total", {}).get("amount") if isinstance(data, dict) else None
                    if cat_total is None:
                        cat_total = sum(self._get_item_value(i) for i in items)
                    
                    total_wealth += cat_total
                    logging.debug(f"  - Personal {cat}: {len(items)} items found (Total: {cat_total}€)")
                except Exception as e:
                    logging.debug(f"Skipping personal {cat}: {e}")

            # 2. Fetch Assets for each Organization
            for org in organizations:
                if not isinstance(org, dict): continue
                org_id = org.get("id")
                org_name = org.get("name") or "Sans nom"
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
                        items = []
                        if isinstance(res, list):
                            items = res
                        elif isinstance(res, dict):
                            data = res.get("result", res)
                            items = self._extract_items(cat, data) if isinstance(data, dict) else []
                        
                        if items:
                            all_assets[cat].extend(items)
                            org_cat_total = sum(self._get_item_value(i) for i in items)
                            total_wealth += org_cat_total
                            logging.info(f"  - Org {org_name} | {cat}: {len(items)} items found (Total: {org_cat_total}€)")
                        else:
                            logging.debug(f"  - Org {org_name} | {cat}: No items found")
                            
                    except Exception as e:
                        logging.warning(f"Error fetching {cat} for org {org_name}: {e}")

            logging.info(f"Final Aggregated Wealth: {total_wealth}€")

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
            logging.error(f"Global Error during fetch: {e}")
            return False

    def _extract_items(self, category, data):
        if not isinstance(data, dict): return []
        # Try different possible keys from Finary API
        return (
            data.get("accounts") or 
            data.get("cryptos") or 
            data.get("fonds_euro") or 
            data.get("scpis") or 
            data.get("real_estates") or 
            data.get("result") or []
        )
