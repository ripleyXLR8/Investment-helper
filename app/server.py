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
        total_assets_count = 0

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
                        total_assets_count += 1

        for g in groups.values():
            g["assets"].sort(key=lambda x: x["balance"], reverse=True)

        return {
            "timestamp": raw.get("timestamp"),
            "total_wealth": summary.get("total_amount", 0),
            "total_assets_count": total_assets_count,
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
    <title>Finary Family Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #030712; --card-bg: #111827; --card-border: #1f2937;
            --accent: #38bdf8; --success: #10b981; --danger: #ef4444; --text-primary: #f9fafb; --text-secondary: #9ca3af;
        }
        body { font-family: 'Plus Jakarta Sans', sans-serif; background-color: var(--bg); color: var(--text-primary); margin: 0; padding: 0; }
        .container { max-width: 1400px; margin: 0 auto; padding: 40px 20px; }
        
        header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 40px; }
        .btn-group { display: flex; gap: 10px; align-items: center; }
        .btn { border: none; padding: 10px 18px; border-radius: 12px; font-weight: 700; font-size: 0.85rem; cursor: pointer; transition: all 0.2s; display: flex; align-items: center; gap: 8px; text-decoration: none; }
        .btn-primary { background: var(--accent); color: #000; }
        .btn-secondary { background: #1f2937; color: var(--text-primary); }
        
        .summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-bottom: 40px; }
        .summary-card { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 24px; padding: 25px; border: 1px solid rgba(255,255,255,0.05); }
        .card-label { color: var(--text-secondary); font-size: 0.85rem; font-weight: 500; margin-bottom: 8px; display: block; }
        .card-value { font-size: 2rem; font-weight: 800; display: block; }
        
        .section-header { display: flex; justify-content: space-between; align-items: baseline; margin: 50px 0 20px 0; border-left: 4px solid var(--accent); padding-left: 15px; }
        .card { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 24px; overflow: hidden; margin-bottom: 30px; }
        table { width: 100%; border-collapse: collapse; }
        th { text-align: left; padding: 16px 20px; background: rgba(255,255,255,0.02); color: var(--text-secondary); font-size: 0.7rem; text-transform: uppercase; }
        td { padding: 16px 20px; border-top: 1px solid var(--card-border); font-size: 0.85rem; vertical-align: top; }
        
        .sub-table { width: 100%; background: rgba(0,0,0,0.25); border-top: 2px solid var(--accent); }
        .sub-row { border-bottom: 1px solid rgba(255,255,255,0.05); }
        .metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-top: 10px; font-size: 0.75rem; }
        .metric-item { background: rgba(255,255,255,0.03); padding: 8px; border-radius: 10px; border: 1px solid rgba(255,255,255,0.05); }
        .metric-label { color: var(--text-secondary); font-size: 0.6rem; display: block; margin-bottom: 2px; }
        
        .tag-badge { font-size: 0.6rem; padding: 2px 8px; border-radius: 6px; font-weight: 800; text-transform: uppercase; background: #374151; color: #d1d5db; }
        .tag-core { background: rgba(16,185,129,0.1); color: #10b981; border: 1px solid rgba(16,185,129,0.2); }
        .tag-spec { background: rgba(239,68,68,0.1); color: #ef4444; border: 1px solid rgba(239,68,68,0.2); }
        
        .positive { color: var(--success); } .negative { color: var(--danger); }
        .bank-logo { width: 32px; height: 32px; border-radius: 8px; background: #fff; padding: 2px; object-fit: contain; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div style="display: flex; align-items: center; gap: 15px;">
                <div style="font-size: 2.2rem;">🏢</div>
                <div><div style="font-weight: 800; font-size: 1.6rem;">Finary Family Dashboard</div><div style="color: var(--text-secondary); font-size: 0.8rem;">Analyse Patrimoniale & Marchés</div></div>
            </div>
            <div class="btn-group">
                <a href="/logs" class="btn btn-secondary">📋 Logs</a>
                <a href="/download" class="btn btn-secondary">💾 JSON</a>
                <button class="btn btn-primary" onclick="triggerUpdate()">⚡ Sync Data</button>
            </div>
        </header>

        <div class="summary-grid">
            <div class="summary-card">
                <span class="card-label">Patrimoine Brut (100%)</span>
                <span class="card-value">{{ "{:,.2f}".format(total_wealth) }} €</span>
            </div>
            <div class="summary-card">
                <span class="card-label">Actifs Répertoriés</span>
                <span class="card-value">{{ total_assets_count }}</span>
            </div>
            <div class="summary-card">
                <span class="card-label">Dernière Synchronisation</span>
                <span class="card-value" style="font-size: 1.4rem; margin-top: 10px; color: var(--accent);">{{ timestamp|format_date }}</span>
            </div>
        </div>

        {% for g_name, g_data in groups.items() %}
        {% if g_data.assets %}
        <div class="section-header">
            <span style="font-size: 1.5rem; font-weight: 800;">{{ g_name }}</span>
            <span style="color: var(--accent); font-weight: 700; font-size: 1.2rem;">{{ "{:,.0f}".format(g_data.total) }} €</span>
        </div>
        
        <div class="card">
            <table>
                <thead>
                    <tr>
                        <th style="width: 40%;">Actif / Institution</th>
                        <th style="width: 15%;">Valeur</th>
                        <th style="width: 15%;">Poids Global</th>
                        <th style="width: 15%;">Performance</th>
                        <th style="width: 15%;">Catégorie</th>
                    </tr>
                </thead>
                <tbody>
                    {% for acc in g_data.assets %}
                    <tr>
                        <td>
                            <div style="display: flex; align-items: center; gap: 15px;">
                                {% if acc.logo %}<img src="{{ acc.logo }}" class="bank-logo">{% else %}<div class="bank-logo" style="background: #334155; display: flex; align-items: center; justify-content: center; font-weight: 800; color: var(--accent);">{{ acc.name[0] }}</div>{% endif %}
                                <div>
                                    <div style="font-weight: 700; font-size: 1rem;">{{ acc.name }}</div>
                                    <div style="font-size: 0.75rem; color: var(--text-secondary);">{{ acc.institution }}</div>
                                    <div style="display: flex; gap: 10px; margin-top: 5px;">
                                        {% for o in acc.owners %}<span style="font-size: 0.65rem; background: rgba(255,255,255,0.05); padding: 2px 6px; border-radius: 4px; color: var(--text-secondary);">👤 {{ o.name }} {{ o.percent }}%</span>{% endfor %}
                                    </div>
                                </div>
                            </div>
                        </td>
                        <td style="font-weight: 800; font-size: 1rem;">{{ "{:,.2f}".format(acc.balance) }} €</td>
                        <td style="font-weight: 700; color: var(--accent);">{{ "{:.1f}".format(acc.weight_global or 0) }}%</td>
                        <td class="{{ 'positive' if acc.upnl_percent >= 0 else 'negative' }}" style="font-weight: 800;">{{ "{:+.2f}%".format(acc.upnl_percent) }}</td>
                        <td><span class="tag-badge">{{ g_name[:-1] }}</span></td>
                    </tr>
                    
                    {% if acc.subs %}
                    <tr>
                        <td colspan="5" style="padding: 0; border: none;">
                            <table class="sub-table">
                                {% for s in acc.subs %}
                                <tr class="sub-row">
                                    <td style="width: 35%; padding-left: 65px;">
                                        <div style="display: flex; align-items: center; gap: 10px;">
                                            <span class="tag-badge {{ 'tag-core' if s.strategic_tag == 'Core' else 'tag-spec' if s.strategic_tag == 'Spec' else '' }}">{{ s.strategic_tag }}</span>
                                            <div style="font-weight: 700;">{{ s.name }}</div>
                                        </div>
                                        <div style="font-size: 0.65rem; color: #64748b; margin-top: 4px;">{{ s.detail or "" }} • {{ s.sector or "Diversifié" }}</div>
                                    </td>
                                    <td style="width: 15%;">
                                        <div style="font-weight: 700; {{ 'color: var(--danger);' if s.value < 0 else '' }}">{{ "{:,.2f}".format(s.value) }} €</div>
                                        <div style="font-size: 0.65rem; color: var(--text-secondary);">{{ s.quantity or "" }} unités</div>
                                    </td>
                                    <td style="width: 50%;">
                                        <div class="metric-grid">
                                            <div class="metric-item"><span class="metric-label">1M / 3M</span><span class="{{ 'positive' if s.perf_1m and s.perf_1m > 0 else 'negative' }}">{{ "{:+.1f}%".format(s.perf_1m or 0) }}</span> / <span class="{{ 'positive' if s.perf_3m and s.perf_3m > 0 else 'negative' }}">{{ "{:+.1f}%".format(s.perf_3m or 0) }}</span></div>
                                            <div class="metric-item"><span class="metric-label">YTD / 1Y</span><span class="{{ 'positive' if s.perf_ytd and s.perf_ytd > 0 else 'negative' }}">{{ "{:+.1f}%".format(s.perf_ytd or 0) }}</span> / <span class="{{ 'positive' if s.perf_1y and s.perf_1y > 0 else 'negative' }}">{{ "{:+.1f}%".format(s.perf_1y or 0) }}</span></div>
                                            <div class="metric-item"><span class="metric-label">Bêta / Vol</span><span style="font-weight: 600;">{{ "{:.2f}".format(s.beta or 1.0) }}</span> / <span style="font-weight: 600;">{{ "{:.1f}%".format(s.volatility or 0) }}</span></div>
                                            <div class="metric-item"><span class="metric-label">Poids Env.</span><span style="color: var(--accent); font-weight: 800;">{{ "{:.1f}%".format(s.weight_envelope or 0) }}</span></div>
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

@app.route("/download")
def download():
    files = [f for f in os.listdir(DATA_DIR) if f.endswith(".json")]
    if not files: return "404", 404
    latest = max(files, key=lambda x: os.path.getmtime(os.path.join(DATA_DIR, x)))
    return send_file(os.path.join(DATA_DIR, latest), as_attachment=True)

@app.route("/logs")
def logs():
    log_path = os.path.join(DATA_DIR, "app.log")
    if not os.path.exists(log_path): return "Aucun log disponible", 404
    return send_file(log_path, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
