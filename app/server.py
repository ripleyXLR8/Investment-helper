import os
import json
import logging
import threading
from datetime import datetime, timezone
from flask import Flask, render_template_string, jsonify, redirect, url_for, send_file
from finary_client import FinaryClient

app = Flask(__name__)
DATA_DIR = os.getenv("DATA_DIR", "/app/data")
FINARY_EMAIL = os.getenv("FINARY_EMAIL")
FINARY_PASSWORD = os.getenv("FINARY_PASSWORD")
FINARY_OTP_SECRET = os.getenv("FINARY_OTP_SECRET")

is_updating = False

def get_item_value(item):
    if not isinstance(item, dict): return 0
    return (
        item.get("balance") or 
        item.get("current_value") or 
        item.get("current_price") or 
        item.get("buying_price") or 0
    )

def calculate_annualized_perf(total_perf_percent, created_at_str):
    if not created_at_str or total_perf_percent is None:
        return None
    try:
        dt_str = created_at_str.replace("Z", "+00:00")
        created_at = datetime.fromisoformat(dt_str)
        now = datetime.now(timezone.utc)
        diff = now - created_at
        years = diff.days / 365.25
        if years <= 0.01: return None
        return ((1 + (total_perf_percent / 100)) ** (1 / years) - 1) * 100
    except:
        return None

def get_financial_data():
    try:
        files = [f for f in os.listdir(DATA_DIR) if f.endswith(".json")]
        if not files: return None
        latest_file = max(files, key=lambda x: os.path.getmtime(os.path.join(DATA_DIR, x)))
        with open(os.path.join(DATA_DIR, latest_file), "r", encoding="utf-8") as f:
            raw = json.load(f)
        
        summary = raw.get("portfolio_summary", {})
        categories = summary.get("categories", {})
        me_slug = raw.get("me", {}).get("result", {}).get("slug")

        groups = {
            "Real Estates": {"items": [], "total": 0},
            "Investments": {"items": [], "total": 0},
            "Cryptos": {"items": [], "total": 0}
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

            partial_balance = get_item_value(item)
            full_balance = partial_balance / user_share if 0 < user_share < 1.0 else partial_balance
            
            upnl = float(item.get("upnl") or item.get("current_upnl") or 0)
            upnl_pct = float(item.get("upnl_percent") or item.get("current_upnl_percent") or 0)
            created_at = item.get("created_at") or item.get("opened_at")
            annualized = calculate_annualized_perf(upnl_pct, created_at)

            name = item.get("display_name") or item.get("name") or "Inconnu"
            institution = item.get("bank", {}).get("name") or item.get("institution_name") or "Autre"
            
            # Security details for investments
            securities = []
            if cat_name == "investments":
                for s in item.get("securities", []):
                    sec_info = s.get("security", {})
                    securities.append({
                        "name": sec_info.get("name"),
                        "isin": sec_info.get("isin"),
                        "quantity": s.get("quantity"),
                        "unit_price": sec_info.get("current_price"),
                        "total_value": s.get("current_value"),
                        "upnl": s.get("current_upnl"),
                        "upnl_pct": s.get("current_upnl_percent")
                    })

            return {
                "name": name, "institution": institution, "owners": owners,
                "logo": item.get("logo_url") or (item.get("crypto", {}).get("logo_url") if "crypto" in item else ""),
                "balance": float(full_balance), "upnl": upnl, "upnl_percent": upnl_pct,
                "annualized_perf": annualized, "securities": securities
            }

        for cat, items in categories.items():
            display_cat = cat.replace("_", " ").title()
            if display_cat in groups:
                for item in items:
                    parsed = parse_item(item, cat)
                    if parsed:
                        groups[display_cat]["items"].append(parsed)
                        groups[display_cat]["total"] += parsed["balance"]

        # Sort items in each group
        for g in groups.values():
            g["items"].sort(key=lambda x: x["balance"], reverse=True)

        total_wealth = sum(g["total"] for g in groups.values())

        return {
            "timestamp": raw.get("timestamp"),
            "total_wealth": total_wealth,
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
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #030712; --card-bg: #111827; --card-border: #1f2937;
            --accent: #38bdf8; --success: #10b981; --danger: #ef4444; --text-primary: #f9fafb; --text-secondary: #9ca3af;
        }
        body { font-family: 'Plus Jakarta Sans', sans-serif; background-color: var(--bg); color: var(--text-primary); margin: 0; padding: 0; }
        .container { max-width: 1200px; margin: 0 auto; padding: 40px 20px; }
        header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 40px; }
        .btn { border: none; padding: 10px 18px; border-radius: 10px; font-weight: 700; font-size: 0.85rem; cursor: pointer; transition: all 0.2s; display: flex; align-items: center; gap: 8px; text-decoration: none; }
        .btn-primary { background: var(--accent); color: #000; }
        .btn-secondary { background: #1f2937; color: var(--text-primary); }
        
        .section-header { display: flex; justify-content: space-between; align-items: baseline; margin: 50px 0 20px 0; border-left: 4px solid var(--accent); padding-left: 15px; }
        .section-title { font-size: 1.5rem; font-weight: 700; }
        .section-total { font-size: 1.1rem; color: var(--accent); font-weight: 600; }
        
        .card { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 20px; overflow: hidden; margin-bottom: 20px; }
        table { width: 100%; border-collapse: collapse; }
        th { text-align: left; padding: 16px 24px; background: rgba(255,255,255,0.02); color: var(--text-secondary); font-size: 0.75rem; text-transform: uppercase; }
        td { padding: 16px 24px; border-top: 1px solid var(--card-border); font-size: 0.9rem; }
        
        .sec-table { width: 100%; background: rgba(0,0,0,0.2); font-size: 0.8rem; }
        .sec-table th { background: transparent; padding: 8px 24px; border: none; color: #6366f1; }
        .sec-table td { padding: 10px 24px; border-top: 1px solid rgba(255,255,255,0.05); }

        .bank-logo { width: 32px; height: 32px; border-radius: 8px; background: #fff; padding: 2px; object-fit: contain; }
        .positive { color: var(--success); } .negative { color: var(--danger); }
        .owner-tag { font-size: 0.7rem; color: var(--text-secondary); margin-top: 4px; }
        .summary-box { background: linear-gradient(135deg, #1e293b, #0f172a); border-radius: 24px; padding: 30px; display: flex; justify-content: space-between; align-items: center; border: 1px solid var(--card-border); }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div style="display: flex; align-items: center; gap: 15px;">
                <div style="width: 48px; height: 48px; background: var(--accent); border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 1.5rem;">🏢</div>
                <div><div style="font-weight: 700; font-size: 1.2rem;">Patrimoine Consolidé</div><div style="color: var(--text-secondary); font-size: 0.8rem;">Analyse détaillée par actifs</div></div>
            </div>
            <div style="display: flex; gap: 10px;">
                <a href="/logs" class="btn btn-secondary">📋 Logs</a>
                <a href="/download" class="btn btn-secondary">💾 JSON</a>
                <button id="updateBtn" class="btn btn-primary" onclick="triggerUpdate()">🔄 Sync Globale</button>
            </div>
        </header>

        <div class="summary-box">
            <div>
                <div style="color: var(--text-secondary); font-size: 0.9rem; margin-bottom: 5px;">Valeur Totale du Patrimoine</div>
                <div style="font-size: 2.5rem; font-weight: 800; color: var(--text-primary);">{{ "{:,.2f}".format(total_wealth) }} €</div>
            </div>
            <div style="text-align: right;">
                <div style="color: var(--text-secondary); font-size: 0.8rem;">Dernière synchronisation</div>
                <div style="font-weight: 600;">{{ timestamp|format_date }}</div>
            </div>
        </div>

        {% for group_name, data in groups.items() %}
        {% if data.items %}
        <div class="section-header">
            <span class="section-title">{{ group_name }}</span>
            <span class="section-total">{{ "{:,.2f}".format(data.total) }} €</span>
        </div>
        
        <div class="card">
            <table>
                <thead>
                    <tr>
                        <th style="width: 40%;">Actif / Institution</th>
                        <th style="width: 20%;">Valeur (100%)</th>
                        <th style="width: 20%;">Perf. Totale</th>
                        <th style="width: 20%;">Annualisée</th>
                    </tr>
                </thead>
                <tbody>
                    {% for acc in data.items %}
                    <tr>
                        <td>
                            <div style="display: flex; align-items: center; gap: 12px;">
                                {% if acc.logo %}<img src="{{ acc.logo }}" class="bank-logo">{% else %}<div class="bank-logo" style="background: #334155; display: flex; align-items: center; justify-content: center; font-weight: 700;">{{ acc.name[0] }}</div>{% endif %}
                                <div>
                                    <div style="font-weight: 700;">{{ acc.name }}</div>
                                    <div style="font-size: 0.75rem; color: var(--text-secondary);">{{ acc.institution }}</div>
                                    {% if acc.owners %}
                                    <div class="owner-tag">
                                        {% for o in acc.owners %}<span style="background: rgba(255,255,255,0.05); padding: 1px 4px; border-radius: 3px; margin-right: 5px;">👤 {{ o.name }} {{ o.percent }}%</span>{% endfor %}
                                    </div>
                                    {% endif %}
                                </div>
                            </div>
                        </td>
                        <td style="font-weight: 700;">{{ "{:,.2f}".format(acc.balance) }} €</td>
                        <td class="{{ 'positive' if acc.upnl >= 0 else 'negative' }}">
                            <div style="font-weight: 600;">{{ "{:+.2f}".format(acc.upnl) }} €</div>
                            <div style="font-size: 0.7rem;">({{ "{:+.2f}".format(acc.upnl_percent) }}%)</div>
                        </td>
                        <td style="font-weight: 600;" class="{{ 'positive' if acc.annualized_perf and acc.annualized_perf >= 0 else 'negative' }}">
                            {% if acc.annualized_perf is not none %}{{ "{:+.2f}".format(acc.annualized_perf) }}%{% else %}-{% endif %}
                        </td>
                    </tr>
                    
                    {% if acc.securities %}
                    <tr>
                        <td colspan="4" style="padding: 0; border: none;">
                            <table class="sec-table">
                                <thead>
                                    <tr>
                                        <th style="width: 40%;">Ligne de Portefeuille</th>
                                        <th style="width: 15%;">Qté</th>
                                        <th style="width: 15%;">PRU / Actuel</th>
                                        <th style="width: 15%;">Valeur</th>
                                        <th style="width: 15%;">Perf.</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for s in acc.securities %}
                                    <tr>
                                        <td>
                                            <div style="font-weight: 600;">{{ s.name }}</div>
                                            <div style="font-size: 0.65rem; color: #64748b;">{{ s.isin or "No ISIN" }}</div>
                                        </td>
                                        <td>{{ "{:,.4f}".format(s.quantity) if s.quantity else "-" }}</td>
                                        <td>
                                            <div style="font-size: 0.7rem; color: var(--text-secondary);">PRU: {{ "{:,.2f}".format(s.total_value - s.upnl) if s.total_value and s.upnl is not none else "-" }}</div>
                                            <div style="font-weight: 600;">Act: {{ "{:,.2f}".format(s.unit_price) if s.unit_price else "-" }}</div>
                                        </td>
                                        <td style="font-weight: 600;">{{ "{:,.2f}".format(s.total_value) if s.total_value else "-" }} €</td>
                                        <td class="{{ 'positive' if s.upnl and s.upnl >= 0 else 'negative' }}">
                                            {% if s.upnl is not none %}{{ "{:+.2f}".format(acc.upnl_percent) }}%{% else %}-{% endif %}
                                        </td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
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
            const btn = document.getElementById('updateBtn'); btn.disabled = true;
            fetch('/update', { method: 'POST' }).then(r => r.json()).then(d => { if (d.status === 'success') setTimeout(() => window.location.reload(), 5000); });
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
        try: FinaryClient(FINARY_EMAIL, FINARY_PASSWORD, FINARY_OTP_SECRET).fetch_and_save(DATA_DIR)
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
