import os
import json
import logging
import google.generativeai as genai

class LLMMapper:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.mapping_file = os.path.join(os.getenv("DATA_DIR", "/app/data"), "ticker_mapping.json")
        self.mapping = self._load_mapping()
        
        if self.api_key:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel('gemini-pro')
        else:
            self.model = None
            logging.warning("GEMINI_API_KEY not found. LLM mapping disabled.")

    def _load_mapping(self):
        if os.path.exists(self.mapping_file):
            try:
                with open(self.mapping_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _save_mapping(self):
        with open(self.mapping_file, 'w') as f:
            json.dump(self.mapping, f, indent=4)

    def resolve_tickers(self, asset_names):
        """
        Takes a list of asset names and returns a dict {name: ticker} using Gemini.
        """
        if not self.model or not asset_names:
            return {}

        # Filter out already known assets
        unknown_assets = [name for name in asset_names if name not in self.mapping]
        if not unknown_assets:
            return {name: self.mapping[name] for name in asset_names if name in self.mapping}

        logging.info(f"--- Asking Gemini to resolve {len(unknown_assets)} assets ---")
        
        prompt = f"""
        Act as a financial data expert. I have a list of investment assets from Finary.
        For each asset, find the most accurate Yahoo Finance Ticker (symbol).
        Rules:
        1. If it's a French stock or ETF, use the .PA suffix (Paris).
        2. If it's a Crypto, use -USD suffix (e.g. BTC-USD).
        3. If it's a cash account or bank, return 'CASH'.
        4. Return ONLY a JSON object where keys are the asset names and values are the tickers.
        
        Assets to resolve:
        {unknown_assets}
        """

        try:
            response = self.model.generate_content(prompt)
            # Basic cleaning of the response to ensure it's valid JSON
            text = response.text.strip()
            if text.startswith("```json"):
                text = text[7:-3].strip()
            elif text.startswith("```"):
                text = text[3:-3].strip()
            
            new_mappings = json.loads(text)
            self.mapping.update(new_mappings)
            self._save_mapping()
            return new_mappings
        except Exception as e:
            logging.error(f"Gemini Error: {e}")
            return {}
