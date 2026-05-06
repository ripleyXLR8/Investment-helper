import yfinance as yf
import pandas as pd
import json
import os
import logging
from datetime import datetime, timedelta

class FinancialEnricher:
    def __init__(self):
        self.cache_file = os.path.join(os.getenv("DATA_DIR", "/app/data"), "yfinance_cache.json")
        self.cache = self._load_cache()

    def _load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _save_cache(self):
        with open(self.cache_file, 'w') as f:
            json.dump(self.cache, f, indent=4)

    def get_ticker(self, item):
        # Deep search for ISIN or Symbol
        sec = item.get("security", {}) or {}
        isin = item.get("isin") or sec.get("isin")
        symbol = item.get("symbol") or sec.get("symbol")
        
        # 1. Crypto handling
        if "crypto" in item or item.get("asset_class") == "crypto":
            sym = symbol or item.get("crypto", {}).get("symbol")
            return f"{sym}-USD" if sym else None

        # 2. Priority to ISIN
        if isin and len(isin) == 12:
            return isin
        
        # 3. Use name as last resort for Search
        return item.get("name") or sec.get("name")

    def enrich(self, data):
        logging.info("--- STARTING FINANCIAL ENRICHMENT ---")
        for cat in ['investments', 'cryptos', 'real_estates']:
            if cat in data:
                logging.info(f"   Enriching category: {cat} ({len(data[cat])} items)")
                for item in data[cat]:
                    ticker = self.get_ticker(item)
                    metrics = self._fetch_metrics(ticker)
                    item.update(metrics)
        
        self._save_cache()
        logging.info("--- ENRICHMENT COMPLETED ---")
        return data

    def _fetch_metrics(self, ticker_name):
        if not ticker_name: return self._get_default_metrics()
        
        # Manual mapping for high-priority assets to ensure 100% success
        mapping = {
            "Plan d'Epargne France du Groupe Air Liquide": "AI.PA",
            "AirLiquide - MyShare": "AI.PA",
            "AirLiquide - Performance Share": "AI.PA",
            "PEA - Bourse Direct": "CW8.PA",
            "Ledger ETHER": "ETH-USD",
            "Ledger BITCOIN": "BTC-USD",
            "Trade Republic": "DBX0AN.PA"
        }
        
        resolved_ticker = mapping.get(ticker_name, ticker_name)
        
        now = datetime.now()
        if resolved_ticker in self.cache:
            cached = self.cache[resolved_ticker]
            # Refresh if data is old OR if it contains only zeros (failed previous fetch)
            has_data = any(cached["data"].get(k, 0) != 0 for k in ["perf_1m", "perf_1y"])
            cached_time = datetime.fromisoformat(cached["timestamp"])
            if (now - cached_time).total_seconds() < 86400 and has_data:
                return cached["data"]

        try:
            logging.debug(f"      Requesting yfinance for {resolved_ticker}...")
            t = yf.Ticker(resolved_ticker)
            hist = t.history(period="2y")
            
            if hist.empty and (len(resolved_ticker) > 15 or " " in resolved_ticker):
                logging.debug(f"       Searching for: {resolved_ticker}")
                search = yf.Search(resolved_ticker, max_results=1)
                results = getattr(search, 'quotes', getattr(search, 'results', []))
                if results:
                    resolved_ticker = results[0]['symbol']
                    logging.info(f"       Found fallback ticker {resolved_ticker}")
                    t = yf.Ticker(resolved_ticker)
                    hist = t.history(period="2y")

            if hist.empty:
                return self._get_default_metrics()

            # Calculate metrics
            current_price = hist['Close'].iloc[-1]
            
            def get_perf(days):
                target_date = hist.index[-1] - timedelta(days=days)
                idx = hist.index.get_indexer([target_date], method='nearest')[0]
                old_price = hist['Close'].iloc[idx]
                return ((current_price / old_price) - 1) * 100

            # YTD calculation
            year_start = datetime(now.year, 1, 1).date()
            ytd_idx = hist.index.get_indexer([pd.Timestamp(year_start)], method='nearest')[0]
            ytd_price = hist['Close'].iloc[ytd_idx]
            
            high_52w = hist['High'].iloc[-252:].max() if len(hist) > 252 else hist['High'].max()

            metrics = {
                "perf_1m": round(get_perf(30), 2),
                "perf_3m": round(get_perf(90), 2),
                "perf_1y": round(get_perf(365), 2),
                "perf_ytd": round(((current_price / ytd_price) - 1) * 100, 2),
                "dist_52w_high": round(((current_price / high_52w) - 1) * 100, 2)
            }
            
            self.cache[resolved_ticker] = {
                "timestamp": now.isoformat(),
                "data": metrics
            }
            return metrics

        except Exception as e:
            logging.error(f"       Error fetching {resolved_ticker}: {e}")
            return self._get_default_metrics()

    def _get_default_metrics(self):
        return {
            "perf_1m": 0.0, "perf_3m": 0.0, "perf_1y": 0.0,
            "perf_ytd": 0.0, "dist_52w_high": 0.0
        }
