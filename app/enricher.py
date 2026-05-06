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
        name = sec.get("name", "")
        
        # Crypto handling
        if "crypto" in item:
            symbol = item.get("crypto", {}).get("symbol")
            return f"{symbol}-USD" if symbol else None

        # Prefer ISIN for precision
        if isin and len(isin) == 12:
            return isin
        
        # Fallback to symbol with exchange suffix
        if symbol:
            exchange = sec.get("exchange", {}).get("name", "").lower()
            if "paris" in exchange: return f"{symbol}.PA"
            if "amsterdam" in exchange: return f"{symbol}.AS"
            if "xetra" in exchange or "frankfurt" in exchange: return f"{symbol}.DE"
            if "london" in exchange: return f"{symbol}.L"
            return symbol
            
        # Last resort: use name for search in _fetch_metrics
        return name if len(name) > 3 else None

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
                    ticker_query = self.get_ticker(sub)
                    if ticker_query:
                        metrics = self._fetch_metrics(ticker_query)
                        sub.update(metrics)
        
        self._save_json(self.cache_path, self.cache)
        return data

    def _fetch_metrics(self, query):
        now = datetime.now()
        if query in self.cache:
            cached = self.cache[query]
            cached_time = datetime.fromisoformat(cached["timestamp"])
            if (now - cached_time).total_seconds() < 86400: # 24h cache
                return cached["data"]

        logging.debug(f"Fetching yfinance data for {query}")
        try:
            # 1. Try direct ticker/ISIN
            t = yf.Ticker(query)
            hist = t.history(period="1y")
            
            # 2. Fallback search if empty (common for European ISINs or names)
            if hist.empty:
                search = yf.Search(query, max_results=1).news # Search returns a News object but Search.results is what we want
                # Actually yf.Search(query).results is the correct way in recent versions
                results = yf.Search(query, max_results=3).results
                if results:
                    best_ticker = results[0]['symbol']
                    logging.info(f"Found ticker {best_ticker} for {query}")
                    t = yf.Ticker(best_ticker)
                    hist = t.history(period="1y")

            if hist.empty:
                # Fill with defaults to avoid NaN in UI
                return self._get_default_metrics()

            current_price = hist['Close'].iloc[-1]
            if pd.isna(current_price): return self._get_default_metrics()
            
            def get_perf(days):
                try:
                    target_date = hist.index[-1] - timedelta(days=days)
                    idx = hist.index.get_indexer([target_date], method='nearest')[0]
                    old_price = hist['Close'].iloc[idx]
                    if pd.isna(old_price) or old_price == 0: return 0.0
                    return ((current_price / old_price) - 1) * 100
                except: return 0.0

            # YTD calculation
            ytd_start = datetime(now.year, 1, 1, tzinfo=hist.index.tz)
            perf_ytd = 0.0
            try:
                idx_ytd = hist.index.get_indexer([ytd_start], method='nearest')[0]
                ytd_price = hist['Close'].iloc[idx_ytd]
                if not pd.isna(ytd_price) and ytd_price > 0:
                    perf_ytd = ((current_price / ytd_price) - 1) * 100
            except: pass

            info = t.info or {}
            metrics = {
                "perf_1m": round(get_perf(30), 2),
                "perf_3m": round(get_perf(90), 2),
                "perf_1y": round(get_perf(365), 2),
                "perf_ytd": round(perf_ytd, 2),
                "beta": round(info.get("beta", 1.0), 2),
                "volatility": round(hist['Close'].pct_change().std() * (252**0.5) * 100, 2) if len(hist) > 10 else 0.0,
                "sector": info.get("sector", "Diversifié"),
                "geography": info.get("country", "Global")
            }
            
            # Clean up NaN in metrics
            for k, v in metrics.items():
                if isinstance(v, float) and pd.isna(v): metrics[k] = 0.0
            
            self.cache[query] = {"timestamp": now.isoformat(), "data": metrics}
            return metrics
        except Exception as e:
            logging.warning(f"Error fetching metrics for {query}: {e}")
            return self._get_default_metrics()

    def _get_default_metrics(self):
        return {
            "perf_1m": 0.0, "perf_3m": 0.0, "perf_1y": 0.0, "perf_ytd": 0.0,
            "beta": 1.0, "volatility": 0.0, "sector": "N/A", "geography": "N/A"
        }
