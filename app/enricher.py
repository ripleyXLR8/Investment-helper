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
        logging.info("--- STARTING FINANCIAL ENRICHMENT ---")
        summary = data.get("portfolio_summary", {})
        categories = summary.get("categories", {})
        total_wealth = float(summary.get("total_amount", 0)) or 1
        
        for cat_name, items in categories.items():
            if not items: continue
            logging.info(f"  Enriching category: {cat_name} ({len(items)} items)")
            
            for item in items:
                if not isinstance(item, dict): continue
                
                # Get name for logging
                name = item.get("name") or (item.get("security") or {}).get("name") or "Unknown"
                
                # Weight calculations
                val = float(item.get("current_value") or item.get("balance") or 0)
                item["weight_global"] = (val / total_wealth) * 100
                
                # Strategic Tag
                asset_id = str(item.get("id") or name)
                item["strategic_tag"] = self.tags.get(asset_id, "Core")
                
                # Yahoo Finance Metrics
                ticker_query = self.get_ticker(item)
                if ticker_query:
                    logging.info(f"    -> {name[:30]:<30} | Ticker: {ticker_query}")
                    metrics = self._fetch_metrics(ticker_query)
                    item.update(metrics)
                else:
                    logging.debug(f"    -> {name[:30]:<30} | No ticker found")
                    item.update(self._get_default_metrics())
        
        logging.info("--- ENRICHMENT COMPLETED ---")
        self._save_json(self.cache_path, self.cache)
        return data

    def _fetch_metrics(self, query):
        # Manual Mapping for French ETFs/Stocks
        mapping = {
            "FR0013412269": "PANX.PA",   # Amundi PEA US Tech
            "FR0011871128": "ESE.PA",     # Amundi PEA S&P 500
            "LU1681047319": "MSE.PA",     # Amundi Euro Stoxx 50
            "FR0011550193": "E600.PA",    # BNP Easy Stoxx Europe 600
            "FR0000053951": "AI.PA",      # Air Liquide (Prime fidélité)
        }
        if query in mapping:
            query = mapping[query]

        now = datetime.now()
        if query in self.cache:
            cached = self.cache[query]
            # Force refresh if cache data is mostly zeros (failed previously)
            metrics = cached.get("data", {})
            has_valid_perf = any(metrics.get(k, 0) != 0 for k in ["perf_1m", "perf_3m", "perf_1y", "perf_ytd"])
            
            cached_time = datetime.fromisoformat(cached["timestamp"])
            if (now - cached_time).total_seconds() < 86400 and has_valid_perf:
                return metrics

        logging.debug(f"      Requesting yfinance for {query}...")
        try:
            # 1. Try as a direct ticker/ISIN
            ticker = yf.Ticker(query)
            hist = ticker.history(period="1y")
            
            # 2. If it's a long string (name) or no data found, try a search
            if hist.empty or len(query.split()) > 1:
                search_query = query
                logging.debug(f"      Searching for: {search_query}")
                search = yf.Search(search_query, max_results=3)
                
                # Handling different yfinance versions for Search results
                results = []
                if hasattr(search, 'quotes'): results = search.quotes
                elif hasattr(search, 'results'): results = search.results
                
                if results:
                    best_ticker = results[0].get('symbol')
                    logging.info(f"      Found fallback ticker {best_ticker} for {query}")
                    ticker = yf.Ticker(best_ticker)
                    hist = ticker.history(period="1y")

            if hist.empty:
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

            info = ticker.info or {}
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
