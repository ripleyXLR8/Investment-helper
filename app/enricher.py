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
                try: return json.load(f)
                except: return {}
        return {}

    def _save_json(self, path, data):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    def get_ticker(self, item):
        # Handle different structures (direct crypto or security object)
        sec = item.get("security", {}) if "security" in item else item
        if not isinstance(sec, dict): return None
        
        isin = sec.get("isin")
        symbol = sec.get("symbol")
        
        # Crypto handling
        if "crypto" in item:
            symbol = item.get("crypto", {}).get("symbol")
            return f"{symbol}-USD" if symbol else None

        if isin and len(isin) == 12: return isin
        
        if symbol:
            exchange = sec.get("exchange", {}).get("name", "").lower()
            if "paris" in exchange: return f"{symbol}.PA"
            if "amsterdam" in exchange: return f"{symbol}.AS"
            if "xetra" in exchange or "frankfurt" in exchange: return f"{symbol}.DE"
            if "london" in exchange: return f"{symbol}.L"
            return symbol
        return None

    def enrich(self, data):
        logging.info("Enriching nested data with financial metrics...")
        summary = data.get("portfolio_summary", {})
        categories = summary.get("categories", {})
        total_wealth = float(summary.get("total_amount", 0)) or 1
        
        for cat_name, accounts in categories.items():
            for acc in accounts:
                if not isinstance(acc, dict): continue
                
                # Weight of account in global portfolio
                acc_balance = float(acc.get("balance") or acc.get("current_value") or 0)
                acc["weight_global"] = (acc_balance / total_wealth) * 100
                
                # Enrich sub-items (Securities in Investments, or Cryptos)
                sub_items = acc.get("securities", []) or acc.get("cryptos", [])
                if not sub_items and cat_name == "cryptos": sub_items = [acc] # Single crypto line
                
                for sub in sub_items:
                    if not isinstance(sub, dict): continue
                    
                    sub_val = float(sub.get("current_value") or sub.get("balance") or 0)
                    sub["weight_global"] = (sub_val / total_wealth) * 100
                    sub["weight_envelope"] = (sub_val / acc_balance * 100) if acc_balance > 0 else 0
                    
                    # Strategic Tag
                    asset_id = str(sub.get("id") or sub.get("name"))
                    sub["strategic_tag"] = self.tags.get(asset_id, "Core")
                    
                    # Yahoo Finance Metrics
                    ticker = self.get_ticker(sub)
                    if ticker:
                        metrics = self._fetch_metrics(ticker)
                        sub.update(metrics)
        
        self._save_json(self.cache_path, self.cache)
        return data

    def _fetch_metrics(self, symbol):
        now = datetime.now()
        if symbol in self.cache:
            cached = self.cache[symbol]
            cached_time = datetime.fromisoformat(cached["timestamp"])
            if (now - cached_time).total_seconds() < 86400: # 24h cache
                return cached["data"]

        logging.debug(f"Fetching yfinance data for {symbol}")
        try:
            t = yf.Ticker(symbol)
            hist = t.history(period="1y")
            if hist.empty: return {}

            current_price = hist['Close'].iloc[-1]
            
            def get_perf(days):
                try:
                    target_date = hist.index[-1] - timedelta(days=days)
                    idx = hist.index.get_indexer([target_date], method='nearest')[0]
                    old_price = hist['Close'].iloc[idx]
                    return ((current_price / old_price) - 1) * 100
                except: return 0.0

            ytd_start = datetime(now.year, 1, 1, tzinfo=hist.index.tz)
            try:
                idx_ytd = hist.index.get_indexer([ytd_start], method='nearest')[0]
                ytd_price = hist['Close'].iloc[idx_ytd]
                perf_ytd = ((current_price / ytd_price) - 1) * 100
            except: perf_ytd = 0.0

            metrics = {
                "perf_1m": get_perf(30),
                "perf_3m": get_perf(90),
                "perf_1y": get_perf(365),
                "perf_ytd": perf_ytd,
                "beta": t.info.get("beta", 1.0),
                "volatility": hist['Close'].pct_change().std() * (252**0.5) * 100 or 0.0,
                "sector": t.info.get("sector", "N/A"),
                "geography": t.info.get("country", "N/A")
            }
            
            self.cache[symbol] = {"timestamp": now.isoformat(), "data": metrics}
            return metrics
        except Exception as e:
            logging.warning(f"Error fetching metrics for {symbol}: {e}")
            return {}
