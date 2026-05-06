import os
import json
import logging
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

class FinancialEnricher:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.tags_path = os.path.join(data_dir, "strategic_tags.json")
        self.cache_path = os.path.join(data_dir, "yfinance_cache.json")
        self.tags = self._load_json(self.tags_path)
        self.cache = self._load_json(self.cache_path)

    def _load_json(self, path):
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_json(self, path, data):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    def get_ticker(self, item, cat_name):
        if cat_name == "cryptos":
            symbol = item.get("crypto", {}).get("symbol")
            return f"{symbol}-USD" if symbol else None
        
        # For investments (Stocks/ETFs)
        sec = item.get("security", {})
        isin = sec.get("isin")
        symbol = sec.get("symbol")
        exchange = sec.get("exchange", {}).get("name", "").lower()
        
        if isin: return isin # yfinance supports some ISINs
        
        if symbol:
            if "paris" in exchange: return f"{symbol}.PA"
            if "amsterdam" in exchange: return f"{symbol}.AS"
            if "xetra" in exchange or "frankfurt" in exchange: return f"{symbol}.DE"
            if "london" in exchange: return f"{symbol}.L"
            return symbol
        return None

    def enrich(self, data):
        logging.info("Enriching data with financial metrics...")
        summary = data.get("portfolio_summary", {})
        categories = summary.get("categories", {})
        total_wealth = sum(float(a.get("balance", 0)) for cat in categories.values() for a in cat) if isinstance(categories, dict) else 1
        
        for cat_name, assets in categories.items():
            # Calculate Envelope Total
            envelope_total = sum(float(a.get("balance", 0)) for a in assets) or 1
            
            for asset in assets:
                # 1. Internal Metrics
                balance = float(asset.get("balance", 0))
                asset["weight_global"] = (balance / total_wealth) * 100
                asset["weight_envelope"] = (balance / envelope_total) * 100
                
                # Strategic Tag
                asset_id = str(asset.get("id", asset.get("name")))
                asset["strategic_tag"] = self.tags.get(asset_id, "Core")
                
                # 2. External Metrics (yfinance)
                ticker_symbol = self.get_ticker(asset, cat_name)
                if ticker_symbol:
                    metrics = self._fetch_metrics(ticker_symbol)
                    asset.update(metrics)
        
        self._save_json(self.cache_path, self.cache)
        return data

    def _fetch_metrics(self, symbol):
        now = datetime.now()
        # Simple cache logic (24h)
        if symbol in self.cache:
            cached = self.cache[symbol]
            if (now - datetime.fromisoformat(cached["timestamp"])).hours < 24:
                return cached["data"]

        logging.debug(f"Fetching yfinance data for {symbol}")
        try:
            t = yf.Ticker(symbol)
            hist = t.history(period="1y")
            if hist.empty: return {}

            current_price = hist['Close'].iloc[-1]
            
            # Momentum
            def get_perf(days):
                target_date = now - timedelta(days=days)
                try:
                    old_price = hist.iloc[hist.index.get_indexer([target_date], method='nearest')[0]]['Close']
                    return ((current_price / old_price) - 1) * 100
                except: return None

            ytd_start = datetime(now.year, 1, 1)
            try:
                ytd_price = hist.iloc[hist.index.get_indexer([ytd_start], method='nearest')[0]]['Close']
                perf_ytd = ((current_price / ytd_price) - 1) * 100
            except: perf_ytd = None

            high_52w = hist['High'].max()
            dist_high = ((current_price / high_52w) - 1) * 100 if high_52w else None

            # Info (Sector, Beta, etc.)
            info = t.info
            
            metrics = {
                "perf_1m": get_perf(30),
                "perf_3m": get_perf(90),
                "perf_1y": get_perf(365),
                "perf_ytd": perf_ytd,
                "dist_high_52w": dist_high,
                "asset_class": info.get("quoteType", "N/A"),
                "sector": info.get("sector", "N/A"),
                "geography": info.get("country", "N/A"),
                "ter": info.get("fees", info.get("expenseRatio", 0)) * 100,
                "beta": info.get("beta"),
                "volatility": hist['Close'].pct_change().std() * (252**0.5) * 100 # Annualized
            }
            
            self.cache[symbol] = {"timestamp": now.isoformat(), "data": metrics}
            return metrics
        except Exception as e:
            logging.warning(f"Error fetching metrics for {symbol}: {e}")
            return {}
