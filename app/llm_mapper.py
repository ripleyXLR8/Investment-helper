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
            try:
                genai.configure(api_key=self.api_key)
                # Try to use a very standard model name
                self.model = genai.GenerativeModel('gemini-3.1-flash-lite-preview')
                # Ping the model to check if it's available
                logging.info("Checking Gemini model availability...")
            except Exception as e:
                logging.error(f"Failed to initialize Gemini: {e}")
                self.model = None
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
        if not self.model or not asset_names:
            return {}

        unknown_assets = [name for name in asset_names if name not in self.mapping]
        if not unknown_assets:
            return {name: self.mapping[name] for name in asset_names if name in self.mapping}

        logging.info(f"--- Asking Gemini to resolve {len(unknown_assets)} assets ---")
        
        prompt = f"""
        Act as a financial data expert. Find the Yahoo Finance Ticker for these assets.
        Rules:
        1. French stocks/ETFs: use .PA suffix.
        2. Cryptos: use -USD suffix.
        3. Cash/Bank: return 'CASH'.
        4. Return ONLY a JSON object: {{"AssetName": "Ticker"}}.
        
        Assets: {unknown_assets}
        """

        try:
            response = self.model.generate_content(prompt)
            text = response.text.strip()
            logging.info(f"Gemini Raw Response: {text}")
            
            # Handle potential markdown formatting in response
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            
            new_mappings = json.loads(text)
            self.mapping.update(new_mappings)
            self._save_mapping()
            logging.info(f"Successfully resolved {len(new_mappings)} assets via Gemini")
            return new_mappings
        except Exception as e:
            logging.error(f"Gemini Error: {e}")
            # If 404, maybe we should try to list models?
            return {}
