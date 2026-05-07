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
        self.manual_mapping = {
            "Plan d'Epargne France du Groupe Air Liquide": "AI.PA",
            "Air Liquide Prime de Fidélité": "AI.PA",
            "AirLiquide - MyShare": "AI.PA",
            "AirLiquide - Performance Share": "AI.PA",
            "PEA - Bourse Direct": "CW8.PA",
            "Ledger ETHER": "ETH-USD",
            "Ledger BITCOIN": "BTC-USD",
            "Trade Republic": "XEON.DE",
            "AXA.PA": "CS.PA",
            "FR0013412269": "UST.PA",
            "FR0011871128": "500.PA",
            "LU1681047319": "MSE.PA",
            "FR0011550193": "ETZ.PA",
            "Amundi PEA US Tech ESG UCITS ETF Acc": "UST.PA",
            "Amundi PEA S&P 500 UCITS ETF Acc": "500.PA",
            "Amundi Euro Stoxx 50 UCITS ETF DR - EUR (D)": "MSE.PA",
            "BNP Paribas Easy Stoxx Europe 600 UCITS ETF": "ETZ.PA"
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
        isin = item.get("isin") or sec.get("isin")
        symbol = item.get("symbol") or sec.get("symbol")
        
        if name in self.manual_mapping: return self.manual_mapping[name]
        if "crypto" in item or item.get("asset_class") == "crypto":
            sym = symbol or item.get("crypto", {}).get("symbol")
            return f"{sym}-USD" if sym else name
        if isin and len(isin) == 12: return isin
        return symbol or name

    def enrich(self, data):
        logging.info("--- STARTING DEEP FINANCIAL ENRICHMENT ---")
        categories = data.get("portfolio_summary", {}).get("categories", {})
        
        # 1. Fetch benchmark data (S&P 500) for manual beta calculation
        self.benchmark_hist = yf.Ticker("^GSPC").history(period="2y")['Close'].pct_change().dropna()
        self.benchmark_hist.index = self.benchmark_hist.index.tz_localize(None)

        # 2. Collect everything to resolve (Accounts + Holdings)
        to_resolve = []
        for cat in ['investments', 'cryptos']:
            if cat in categories:
                for account in categories[cat]:
                    to_resolve.append(self.get_ticker(account))
                    # Check sub-items (securities)
                    for holding in account.get("holdings", []):
                        to_resolve.append(self.get_ticker(holding))
        
        if to_resolve:
            self.llm.resolve_tickers(list(set([t for t in to_resolve if t])))

        # 2. Enrich everything
        for cat in ['investments', 'cryptos', 'real_estates']:
            if cat in categories:
                for account in categories[cat]:
                    account.update(self._fetch_metrics(self.get_ticker(account)))
                    # Deep enrichment for individual stocks/ETFs
                    if "holdings" in account:
                        for holding in account["holdings"]:
                            ticker = self.get_ticker(holding)
                            resolved = self.llm.mapping.get(ticker, ticker)
                            metrics = self._fetch_metrics(ticker)
                            holding.update(metrics)
                            holding["ticker"] = resolved
                            if "security" in holding:
                                holding["security"].update(metrics)
                                holding["security"]["ticker"] = resolved
                    
                    # Finary sometimes uses 'securities' instead of 'holdings'
                    if "securities" in account:
                        for s in account["securities"]:
                            ticker = self.get_ticker(s)
                            resolved = self.llm.mapping.get(ticker, ticker)
                            metrics = self._fetch_metrics(ticker)
                            s.update(metrics)
                            s["ticker"] = resolved
                            if "security" in s:
                                s["security"].update(metrics)
                                s["security"]["ticker"] = resolved
        
        self._save_cache()
        logging.info("--- DEEP ENRICHMENT COMPLETED ---")
        return data

    def _fetch_metrics(self, ticker_name):
        if not ticker_name: return self._get_default_metrics()
        resolved_ticker = self.llm.mapping.get(ticker_name, ticker_name)
        if resolved_ticker == "CASH": return self._get_default_metrics()

        now = datetime.now()
        if resolved_ticker in self.cache:
            cached = self.cache[resolved_ticker]
            cached_time = datetime.fromisoformat(cached["timestamp"])
            if (now - cached_time).total_seconds() < 43200: # 12h cache
                return cached["data"]

        try:
            t = yf.Ticker(resolved_ticker)
            hist = t.history(period="2y")
            if hist.empty: return self._get_default_metrics()

            # Fix for NaN values often present in last row for European tickers
            hist = hist.dropna(subset=['Close'])
            if hist.empty: return self._get_default_metrics()

            hist.index = hist.index.tz_localize(None)
            current_price = float(hist['Close'].iloc[-1])
            
            def get_perf(days):
                target_date = hist.index[-1] - timedelta(days=days)
                idx = hist.index.get_indexer([target_date], method='nearest')[0]
                old_price = hist['Close'].iloc[idx]
                return ((current_price / old_price) - 1) * 100 if old_price != 0 else 0

            year_start = datetime(now.year, 1, 1)
            ytd_idx = hist.index.get_indexer([year_start], method='nearest')[0]
            ytd_price = hist['Close'].iloc[ytd_idx]
            high_52w = hist['High'].iloc[-252:].max() if len(hist) > 0 else 0

            # Calculation of Volatility (annualized)
            daily_returns = hist['Close'].pct_change().dropna()
            volatility = float(daily_returns.std() * (252**0.5) * 100) if not daily_returns.empty else 0.0

            # Manual Beta calculation against S&P 500
            beta_manual = 1.0
            if not daily_returns.empty and not self.benchmark_hist.empty:
                try:
                    # Align returns
                    combined = pd.concat([daily_returns, self.benchmark_hist], axis=1).dropna()
                    if len(combined) > 20:
                        cov = combined.cov().iloc[0, 1]
                        var = combined.iloc[:, 1].var()
                        beta_manual = cov / var if var != 0 else 1.0
                except:
                    pass

            # Beta from yfinance info
            beta_yahoo = t.info.get('beta')

            metrics = {
                "perf_1m": round(get_perf(30), 2),
                "perf_3m": round(get_perf(90), 2),
                "perf_1y": round(get_perf(365), 2),
                "perf_ytd": round(((current_price / ytd_price) - 1) * 100, 2) if ytd_price != 0 else 0,
                "beta": round(float(beta_yahoo) if beta_yahoo else 0, 2),
                "beta_manual": round(float(beta_manual), 2),
                "volatility": round(volatility, 2),
                "dist_52w_high": round(((current_price / high_52w) - 1) * 100, 2) if high_52w != 0 else 0
            }
            self.cache[resolved_ticker] = {"timestamp": now.isoformat(), "data": metrics}
            return metrics
        except:
            return self._get_default_metrics()

    def _get_default_metrics(self):
        return {"perf_1m": 0.0, "perf_3m": 0.0, "perf_1y": 0.0, "perf_ytd": 0.0, "beta": 0.0, "beta_manual": 1.0, "volatility": 0.0, "dist_52w_high": 0.0}
