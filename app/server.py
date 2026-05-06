import os
import json
import logging
import threading
from flask import Flask, render_template_string, jsonify, redirect, url_for, send_file
from finary_client import FinaryClient

app = Flask(__name__)
DATA_DIR = os.getenv("DATA_DIR", "/app/data")
FINARY_EMAIL = os.getenv("FINARY_EMAIL")
FINARY_PASSWORD = os.getenv("FINARY_PASSWORD")
FINARY_OTP_SECRET = os.getenv("FINARY_OTP_SECRET")

is_updating = False

# HTML template remains mostly the same, but we ensure values are handled correctly.
# (I'll keep the template short in this write_to_file but ensure logic is solid)

def get_item_value(item):
    if not isinstance(item, dict): return 0
    return (
        item.get("balance") or 
        item.get("current_value") or 
        item.get("current_price") or 
        item.get("buying_price") or 0
    )

def get_financial_data():
    try:
        files = [f for f in os.listdir(DATA_DIR) if f.endswith(".json")]
        if not files: return None
        latest_file = max(files, key=lambda x: os.path.getmtime(os.path.join(DATA_DIR, x)))
        with open(os.path.join(DATA_DIR, latest_file), "r", encoding="utf-8") as f:
            raw = json.load(f)
        
        summary = raw.get("portfolio_summary", {})
        categories = summary.get("categories", {})
        accounts = []
        seen_ids = set()

        def add_acc(item, cat_name):
            if not isinstance(item, dict): return
            # Better ID detection to avoid duplicates across Personal/Family views
            item_id = str(item.get("id") or item.get("slug") or item.get("name") or "")
            if item_id in seen_ids: return
            seen_ids.add(item_id)
            
            balance = get_item_value(item)
            name = item.get("display_name") or item.get("name") or "Inconnu"
            
            # Crypto specific name formatting
            if cat_name == "cryptos" and "crypto" in item:
                crypto_info = item.get("crypto", {})
                symbol = crypto_info.get("symbol", "")
                quantity = item.get("quantity")
                if quantity:
                    name = f"{quantity} {symbol}" if symbol else f"{quantity} Crypto"
                elif not name or name == "Inconnu":
                    name = crypto_info.get("name") or symbol or "Crypto"

            institution = item.get("bank", {}).get("name") or item.get("institution_name") or ""
            if not institution:
                if cat_name == "real_estates": institution = "Immobilier"
                elif cat_name == "cryptos": institution = item.get("crypto", {}).get("name", "Portefeuille Crypto")
                else: institution = "Autre"

            accounts.append({
                "name": name, "institution": institution,
                "logo": item.get("logo_url") or (item.get("crypto", {}).get("logo_url") if "crypto" in item else ""),
                "balance": float(balance), 
                "upnl": float(item.get("upnl") or item.get("current_upnl") or 0),
                "upnl_percent": float(item.get("upnl_percent") or item.get("current_upnl_percent") or 0),
                "type": cat_name.replace("_", " ").title()
            })

        for cat, items in categories.items():
            if isinstance(items, list):
                for item in items: add_acc(item, cat)

        return {
            "timestamp": raw.get("timestamp"), # Dashboard format_date handles it
            "organizations": raw.get("organizations", []),
            "total_wealth": summary.get("total_amount", 0),
            "accounts": sorted(accounts, key=lambda x: x['balance'], reverse=True)
        }
    except Exception as e:
        logging.error(f"Error parsing financial data: {e}")
        return None

# Rest of the file (HTML_TEMPLATE and routes) remains the same as previous version
# I'll just include the full content to be safe and ensure everything is updated.

# [REUSE HTML_TEMPLATE from previous turn]
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
        .btn-group { display: flex; gap: 12px; align-items: center; }
        .btn { border: none; padding: 10px 18px; border-radius: 10px; font-weight: 700; font-size: 0.85rem; cursor: pointer; transition: all 0.2s; display: flex; align-items: center; gap: 8px; text-decoration: none; }
        .btn-primary { background: var(--accent); color: #000; }
        .btn-secondary { background: #1f2937; color: var(--text-primary); }
        .summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-bottom: 40px; }
        .card { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 20px; padding: 24px; }
        .card-label { color: var(--text-secondary); font-size: 0.85rem; font-weight: 500; margin-bottom: 8px; display: block; }
        .card-value { font-size: 1.8rem; font-weight: 700; display: block; }
        table { width: 100%; border-collapse: separate; border-spacing: 0; background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 16px; overflow: hidden; }
        th { text-align: left; padding: 16px 24px; background: rgba(255,255,255,0.02); color: var(--text-secondary); font-size: 0.75rem; text-transform: uppercase; }
        td { padding: 16px 24px; border-top: 1px solid var(--card-border); font-size: 0.9rem; }
        .bank-logo { width: 28px; height: 28px; border-radius: 6px; background: #fff; padding: 2px; object-fit: contain; }
        .badge { padding: 4px 8px; border-radius: 6px; font-size: 0.65rem; font-weight: 700; text-transform: uppercase; background: rgba(56,189,248,0.1); color: var(--accent); }
        .positive { color: var(--success); } .negative { color: var(--danger); }
        .spinner { width: 14px; height: 14px; border: 2px solid rgba(0,0,0,0.2); border-top: 2px solid #000; border-radius: 50%; animation: spin 1s linear infinite; display: none; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        .updating .spinner { display: block; } .updating .icon { display: none; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div style="display: flex; align-items: center; gap: 15px;">
                <div style="width: 48px; height: 48px; background: linear-gradient(135deg, var(--accent), #818cf8); border-radius: 12px; display: flex; align-items: center; justify-content: center; font-weight: 700;">👪</div>
                <div><div style="font-weight: 700;">Patrimoine Consolidé</div><div style="color: var(--text-secondary); font-size: 0.8rem;">Espaces : {% for org in organizations %}{{ org.name or "Famille" }}{% if not loop.last %}, {% endif %}{% endfor %}</div></div>
            </div>
            <div class="btn-group">
                <a href="/logs" class="btn btn-secondary">📋 Logs</a>
                <a href="/download" class="btn btn-secondary">💾 JSON</a>
                <button id="updateBtn" class="btn btn-primary" onclick="triggerUpdate()"><span class="spinner"></span><span class="icon">🔄</span><span id="btnText">Sync Globale</span></button>
            </div>
        </header>

        <div class="summary-grid">
            <div class="card"><span class="card-label">Patrimoine Brut</span><span class="card-value">{{ "{:,.2f}".format(total_wealth) }} €</span></div>
            <div class="card"><span class="card-label">Actifs répertoriés</span><span class="card-value">{{ accounts|length }}</span></div>
            <div class="card"><span class="card-label">Dernière Sync</span><span class="card-value" style="font-size: 1.2rem; margin-top: 10px;">{{ timestamp|format_date }}</span></div>
        </div>

        <table>
            <thead><tr><th>Actif / Institution</th><th>Catégorie</th><th>Valeur Actuelle</th><th>Performance</th></tr></thead>
            <tbody>
                {% for acc in accounts %}
                <tr>
                    <td>
                        <div style="display: flex; align-items: center; gap: 12px;">
                            {% if acc.logo %}
                            <img src="{{ acc.logo }}" class="bank-logo" onerror="this.style.display='none'">
                            {% else %}
                            <div class="bank-logo" style="background: var(--card-border); display: flex; align-items: center; justify-content: center; font-size: 0.8rem;">{{ acc.name[0] }}</div>
                            {% endif %}
                            <div><div style="font-weight: 600;">{{ acc.name }}</div><div style="font-size: 0.75rem; color: var(--text-secondary);">{{ acc.institution }}</div></div>
                        </div>
                    </td>
                    <td><span class="badge">{{ acc.type }}</span></td>
                    <td style="font-weight: 700;">{{ "{:,.2f}".format(acc.balance) }} €</td>
                    <td class="{{ 'positive' if acc.upnl >= 0 else 'negative' }}">
                        {% if acc.upnl != 0 %}
                        {{ "+" if acc.upnl >= 0 }}{{ "{:,.2f}".format(acc.upnl) }} € ({{ "{:.2f}".format(acc.upnl_percent) }}%)
                        {% else %}-{% endif %}
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    <script>
        function triggerUpdate() {
            const btn = document.getElementById('updateBtn'); btn.disabled = true; btn.classList.add('updating');
            fetch('/update', { method: 'POST' }).then(r => r.json()).then(d => { if (d.status === 'success') setTimeout(() => window.location.reload(), 5000); else alert('Erreur'); });
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
