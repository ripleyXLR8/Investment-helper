import os
import json
import logging
import threading
from datetime import datetime, timezone
from flask import Flask, render_template_string, jsonify, redirect, url_for, send_file, request
from finary_client import FinaryClient

app = Flask(__name__)
DATA_DIR = os.getenv("DATA_DIR", "/app/data")
FINARY_EMAIL = os.getenv("FINARY_EMAIL")
FINARY_PASSWORD = os.getenv("FINARY_PASSWORD")
FINARY_OTP_SECRET = os.getenv("FINARY_OTP_SECRET")

is_updating = False

def get_financial_data():
    try:
        files = [f for f in os.listdir(DATA_DIR) if f.endswith(".json") and "finary_data" in f]
        if not files: return None
        latest_file = max(files, key=lambda x: os.path.getmtime(os.path.join(DATA_DIR, x)))
        with open(os.path.join(DATA_DIR, latest_file), "r", encoding="utf-8") as f:
            raw = json.load(f)
        
        summary = raw.get("portfolio_summary", {})
        categories = summary.get("categories", {})
        me_slug = raw.get("me", {}).get("result", {}).get("slug")

        groups = {
            "Real Estates": {"assets": [], "total": 0},
            "Investments": {"assets": [], "total": 0},
            "Cryptos": {"assets": [], "total": 0}
        }
        
        seen_ids = set()

        def parse_item(item, cat_name):
            if not isinstance(item, dict): return None
            item_id = str(item.get("id") or item.get("slug") or item.get("name") or "")
            if item_id in seen_ids: return None
            seen_ids.add(item_id)

            owners = []
            user_share = 1.0
            repartition = item.get("ownership_repartition", [])
            if repartition:
                for r in repartition:
                    member = r.get("membership", {}).get("member", {})
                    name = member.get("firstname") or member.get("fullname") or "Inconnu"
                    share = float(r.get("share", 0))
                    owners.append({"name": name, "percent": int(share * 100)})
                    if member.get("slug") == me_slug:
                        user_share = share

            partial_balance = float(item.get("balance") or item.get("current_value") or 0)
            full_balance = partial_balance / user_share if 0 < user_share < 1.0 else partial_balance
            
            upnl_pct = float(item.get("upnl_percent") or item.get("current_upnl_percent") or 0)
            
            subs = []
            if cat_name == "investments":
                for s in item.get("securities", []):
                    sec_info = s.get("security", {})
                    subs.append({
                        "name": sec_info.get("name"),
                        "detail": sec_info.get("isin"),
                        "quantity": s.get("quantity"),
                        "pru": s.get("buying_price"),
                        "unit_price": sec_info.get("current_price"),
                        "value": s.get("current_value"),
                        "perf": s.get("current_upnl_percent"),
                        # Enriched fields
                        "perf_1m": s.get("perf_1m"), "perf_3m": s.get("perf_3m"), "perf_1y": s.get("perf_1y"), "perf_ytd": s.get("perf_ytd"),
                        "beta": s.get("beta"), "volatility": s.get("volatility"),
                        "sector": s.get("sector"), "geography": s.get("geography"),
                        "weight_global": s.get("weight_global"), "weight_envelope": s.get("weight_envelope"),
                        "strategic_tag": s.get("strategic_tag", "Core"),
                        "id": str(s.get("id", sec_info.get("name")))
                    })
            elif cat_name == "real_estates":
                for l in item.get("loans", []):
                    subs.append({
                        "name": f"Emprunt: {l.get('name')}",
                        "value": -float(l.get("balance", 0)),
                        "detail": "Passif"
                    })

            return {
                "name": item.get("display_name") or item.get("name") or "Inconnu",
                "institution": item.get("bank", {}).get("name") or item.get("institution_name") or "",
                "owners": owners,
                "logo": item.get("logo_url") or (item.get("crypto", {}).get("logo_url") if "crypto" in item else ""),
                "balance": float(full_balance),
                "upnl_percent": upnl_pct,
                "subs": subs,
                "weight_global": item.get("weight_global")
            }

        for cat, items in categories.items():
            display_cat = cat.replace("_", " ").title()
            if display_cat in groups:
                for item in items:
                    parsed = parse_item(item, cat)
                    if parsed:
                        groups[display_cat]["assets"].append(parsed)
                        groups[display_cat]["total"] += parsed["balance"]

        for g in groups.values():
            g["assets"].sort(key=lambda x: x["balance"], reverse=True)

        return {
            "timestamp": raw.get("timestamp"),
            "total_wealth": summary.get("total_amount", 0),
            "groups": groups
        }
    except Exception as e:
        logging.error(f"Error parsing financial data: {e}")
        return None

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Finary Advanced Analytics</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #030712; --card-bg: #111827; --card-border: #1f2937;
            --accent: #38bdf8; --success: #10b981; --danger: #ef4444; --text-primary: #f9fafb; --text-secondary: #9ca3af;
        }
        body { font-family: 'Plus Jakarta Sans', sans-serif; background-color: var(--bg); color: var(--text-primary); margin: 0; padding: 0; }
        .container { max-width: 1400px; margin: 0 auto; padding: 40px 20px; }
        header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; }
        .section-header { display: flex; justify-content: space-between; align-items: baseline; margin: 40px 0 15px 0; border-left: 4px solid var(--accent); padding-left: 15px; }
        .card { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 20px; overflow: hidden; margin-bottom: 25px; }
        table { width: 100%; border-collapse: collapse; }
        th { text-align: left; padding: 12px 20px; background: rgba(255,255,255,0.02); color: var(--text-secondary); font-size: 0.7rem; text-transform: uppercase; }
        td { padding: 12px 20px; border-top: 1px solid var(--card-border); font-size: 0.85rem; vertical-align: top; }
        
        .sub-table { width: 100%; background: rgba(0,0,0,0.25); border-top: 2px solid var(--accent); }
        .sub-row { border-bottom: 1px solid rgba(255,255,255,0.05); }
        .metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-top: 8px; font-size: 0.75rem; }
        .metric-item { background: rgba(255,255,255,0.03); padding: 5px 8px; border-radius: 6px; }
        .metric-label { color: var(--text-secondary); font-size: 0.65rem; display: block; }
        
        .tag-badge { font-size: 0.6rem; padding: 2px 6px; border-radius: 4px; font-weight: 700; text-transform: uppercase; background: #374151; color: #d1d5db; }
        .tag-core { background: rgba(16,185,129,0.1); color: #10b981; }
        .tag-spec { background: rgba(239,68,68,0.1); color: #ef4444; }
        
        .positive { color: var(--success); } .negative { color: var(--danger); }
        .bank-logo { width: 28px; height: 28px; border-radius: 6px; background: #fff; padding: 2px; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div style="display: flex; align-items: center; gap: 15px;">
                <div style="font-size: 2rem;">🚀</div>
                <div><div style="font-weight: 800; font-size: 1.5rem;">Advanced Analytics</div><div style="color: var(--text-secondary); font-size: 0.8rem;">Momentum & Risk Engine Active</div></div>
            </div>
            <div style="display: flex; gap: 10px;">
                <button class="btn btn-secondary" onclick="window.location.reload()">🔄 Refresh</button>
                <button class="btn btn-primary" onclick="triggerUpdate()">⚡ Sync Data</button>
            </div>
        </header>

        {% for g_name, g_data in groups.items() %}
        {% if g_data.assets %}
        <div class="section-header">
            <span style="font-size: 1.4rem; font-weight: 800;">{{ g_name }}</span>
            <span style="color: var(--accent); font-weight: 700;">{{ "{:,.0f}".format(g_data.total) }} €</span>
        </div>
        
        <div class="card">
            <table>
                <thead>
                    <tr>
                        <th style="width: 40%;">Actif / Enveloppe</th>
                        <th style="width: 15%;">Valeur</th>
                        <th style="width: 15%;">Poids Global</th>
                        <th style="width: 15%;">Perf. Totale</th>
                        <th style="width: 15%;">Type</th>
                    </tr>
                </thead>
                <tbody>
                    {% for acc in g_data.assets %}
                    <tr>
                        <td>
                            <div style="display: flex; align-items: center; gap: 12px;">
                                {% if acc.logo %}<img src="{{ acc.logo }}" class="bank-logo">{% else %}<div class="bank-logo" style="background: #334155;"></div>{% endif %}
                                <div>
                                    <div style="font-weight: 700;">{{ acc.name }}</div>
                                    <div style="font-size: 0.7rem; color: var(--text-secondary);">{{ acc.institution }}</div>
                                </div>
                            </div>
                        </td>
                        <td style="font-weight: 700;">{{ "{:,.2f}".format(acc.balance) }} €</td>
                        <td style="font-weight: 600; color: var(--accent);">{{ "{:.1f}".format(acc.weight_global or 0) }}%</td>
                        <td class="{{ 'positive' if acc.upnl_percent >= 0 else 'negative' }}" style="font-weight: 700;">{{ "{:+.2f}%".format(acc.upnl_percent) }}</td>
                        <td><span class="tag-badge">{{ g_name[:-1] }}</span></td>
                    </tr>
                    
                    {% if acc.subs %}
                    <tr>
                        <td colspan="5" style="padding: 0; border: none;">
                            <table class="sub-table">
                                {% for s in acc.subs %}
                                <tr class="sub-row">
                                    <td style="width: 35%; padding-left: 60px;">
                                        <div style="display: flex; align-items: center; gap: 8px;">
                                            <span class="tag-badge {{ 'tag-core' if s.strategic_tag == 'Core' else 'tag-spec' if s.strategic_tag == 'Spec' else '' }}">{{ s.strategic_tag }}</span>
                                            <div style="font-weight: 700;">{{ s.name }}</div>
                                        </div>
                                        <div style="font-size: 0.65rem; color: #64748b; margin-top: 2px;">{{ s.detail or "" }} • {{ s.sector or "Diversifié" }}</div>
                                    </td>
                                    <td style="width: 15%;">
                                        <div style="font-weight: 700;">{{ "{:,.2f}".format(s.value) }} €</div>
                                        <div style="font-size: 0.65rem; color: var(--text-secondary);">{{ s.quantity or "" }} unités</div>
                                    </td>
                                    <td style="width: 50%;">
                                        <div class="metric-grid">
                                            <div class="metric-item"><span class="metric-label">1M / 3M</span><span class="{{ 'positive' if s.perf_1m and s.perf_1m > 0 else 'negative' }}">{{ "{:+.1f}%".format(s.perf_1m or 0) }}</span> / <span class="{{ 'positive' if s.perf_3m and s.perf_3m > 0 else 'negative' }}">{{ "{:+.1f}%".format(s.perf_3m or 0) }}</span></div>
                                            <div class="metric-item"><span class="metric-label">YTD / 1Y</span><span class="{{ 'positive' if s.perf_ytd and s.perf_ytd > 0 else 'negative' }}">{{ "{:+.1f}%".format(s.perf_ytd or 0) }}</span> / <span class="{{ 'positive' if s.perf_1y and s.perf_1y > 0 else 'negative' }}">{{ "{:+.1f}%".format(s.perf_1y or 0) }}</span></div>
                                            <div class="metric-item"><span class="metric-label">Bêta / Vol</span><span>{{ "{:.2f}".format(s.beta or 1.0) }}</span> / <span>{{ "{:.1f}%".format(s.volatility or 0) }}</span></div>
                                            <div class="metric-item"><span class="metric-label">Poids Env.</span><span style="color: var(--accent); font-weight: 700;">{{ "{:.1f}%".format(s.weight_envelope or 0) }}</span></div>
                                        </div>
                                    </td>
                                </tr>
                                {% endfor %}
                            </table>
                        </td>
                    </tr>
                    {% endif %}
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% endif %}
        {% endfor %}
    </div>
    <script>
        function triggerUpdate() {
            const b = document.querySelector('.btn-primary'); b.innerText = "⏳ Synchronisation..."; b.disabled = true;
            fetch('/update', { method: 'POST' }).then(() => setTimeout(() => window.location.reload(), 10000));
        }
    </script>
</body>
</html>
"""

@app.template_filter('format_date')
def format_date_filter(date_str):
    if not date_str: return "N/A"
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y %H:%M")
    except: return date_str

@app.route("/")
def index():
    data = get_financial_data()
    if not data: return "<h1>Initialisation...</h1>"
    return render_template_string(HTML_TEMPLATE, **data)

@app.route("/update", methods=["POST"])
def update():
    global is_updating
    if is_updating: return jsonify({"status": "error"}), 400
    def run():
        global is_updating
        is_updating = True
        try:
            client = FinaryClient(FINARY_EMAIL, FINARY_PASSWORD, FINARY_OTP_SECRET)
            client.fetch_and_save(DATA_DIR)
        finally: is_updating = False
    threading.Thread(target=run).start()
    return jsonify({"status": "success"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
