import yfinance as yf
import pandas as pd
import json
import os
import logging
from datetime import datetime, timedelta
from llm_mapper import LLMMapper

class FinancialEnricher:
    def __init__(self):
        self.data_dir = os.getenv("DATA_DIR", "/app/data")
        self.cache_file = os.path.join(self.data_dir, "yfinance_cache.json")
        self.cache = self._load_cache()
        self.llm = LLMMapper()
        # Hardcoded overrides for peace of mind
        self.manual_mapping = {
            "Plan d'Epargne France du Groupe Air Liquide": "AI.PA",
            "AirLiquide - MyShare": "AI.PA",
            "AirLiquide - Performance Share": "AI.PA",
            "PEA - Bourse Direct": "CW8.PA",
            "Ledger ETHER": "ETH-USD",
            "Ledger BITCOIN": "BTC-USD",
            "Trade Republic": "DBX0AN.PA"
        }

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
        sec = item.get("security", {}) or {}
        name = item.get("name") or sec.get("name")
        
        # Priority 1: Manual Mapping
        if name in self.manual_mapping:
            return self.manual_mapping[name]

        # Priority 2: Crypto handling
        isin = item.get("isin") or sec.get("isin")
        symbol = item.get("symbol") or sec.get("symbol")
        if "crypto" in item or item.get("asset_class") == "crypto":
            sym = symbol or item.get("crypto", {}).get("symbol")
            return f"{sym}-USD" if sym else name

        # Priority 3: ISIN
        if isin and len(isin) == 12:
            return isin
        
        return name

    def enrich(self, data):
        logging.info("--- STARTING FINANCIAL ENRICHMENT ---")
        categories = data.get("portfolio_summary", {}).get("categories", {})
        
        all_assets = []
        for cat in ['investments', 'cryptos', 'real_estates']:
            if cat in categories:
                for item in categories[cat]:
                    ticker = self.get_ticker(item)
                    if ticker and ticker not in self.manual_mapping.values():
                        all_assets.append(ticker)
        
        if all_assets:
            self.llm.resolve_tickers(list(set(all_assets)))

        for cat in ['investments', 'cryptos', 'real_estates']:
            if cat in categories:
                logging.info(f"   Enriching category: {cat} ({len(categories[cat])} items)")
                for item in categories[cat]:
                    ticker = self.get_ticker(item)
                    metrics = self._fetch_metrics(ticker)
                    item.update(metrics)
        
        self._save_cache()
        logging.info("--- ENRICHMENT COMPLETED ---")
        return data

    def _fetch_metrics(self, ticker_name):
        if not ticker_name: return self._get_default_metrics()
        
        resolved_ticker = self.llm.mapping.get(ticker_name, ticker_name)
        if resolved_ticker == "CASH": return self._get_default_metrics()

        now = datetime.now()
        if resolved_ticker in self.cache:
            cached = self.cache[resolved_ticker]
            has_data = any(cached["data"].get(k, 0) != 0 for k in ["perf_1m", "perf_1y"])
            cached_time = datetime.fromisoformat(cached["timestamp"])
            if (now - cached_time).total_seconds() < 86400 and has_data:
                return cached["data"]

        try:
            logging.debug(f"      Requesting yfinance for {resolved_ticker}...")
            t = yf.Ticker(resolved_ticker)
            hist = t.history(period="2y")
            
            if hist.empty:
                return self._get_default_metrics()

            # FIX: Remove timezone info to allow comparison with 'now'
            hist.index = hist.index.tz_localize(None)
            current_price = hist['Close'].iloc[-1]
            
            def get_perf(days):
                target_date = hist.index[-1] - timedelta(days=days)
                idx = hist.index.get_indexer([target_date], method='nearest')[0]
                old_price = hist['Close'].iloc[idx]
                return ((current_price / old_price) - 1) * 100 if old_price != 0 else 0

            # YTD calculation
            year_start = datetime(now.year, 1, 1)
            ytd_idx = hist.index.get_indexer([year_start], method='nearest')[0]
            ytd_price = hist['Close'].iloc[ytd_idx]
            
            high_52w = hist['High'].iloc[-252:].max() if len(hist) > 0 else 0

            metrics = {
                "perf_1m": round(get_perf(30), 2),
                "perf_3m": round(get_perf(90), 2),
                "perf_1y": round(get_perf(365), 2),
                "perf_ytd": round(((current_price / ytd_price) - 1) * 100, 2) if ytd_price != 0 else 0,
                "dist_52w_high": round(((current_price / high_52w) - 1) * 100, 2) if high_52w != 0 else 0
            }
            
            self.cache[resolved_ticker] = {"timestamp": now.isoformat(), "data": metrics}
            return metrics

        except Exception as e:
            logging.error(f"       Error fetching {resolved_ticker}: {e}")
            return self._get_default_metrics()

    def _get_default_metrics(self):
        return {
            "perf_1m": 0.0, "perf_3m": 0.0, "perf_1y": 0.0,
            "perf_ytd": 0.0, "dist_52w_high": 0.0
        }
