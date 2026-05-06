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

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Finary Dashboard | {{ me.fullname }}</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #030712; --card-bg: #111827; --card-border: #1f2937;
            --accent: #38bdf8; --accent-hover: #0ea5e9; --secondary: #334155;
            --success: #10b981; --danger: #ef4444; --text-primary: #f9fafb; --text-secondary: #9ca3af;
        }
        body { font-family: 'Plus Jakarta Sans', sans-serif; background-color: var(--bg); color: var(--text-primary); margin: 0; padding: 0; }
        .container { max-width: 1200px; margin: 0 auto; padding: 40px 20px; }
        header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 40px; }
        .btn-group { display: flex; gap: 12px; align-items: center; }
        .btn { border: none; padding: 10px 18px; border-radius: 10px; font-weight: 700; font-size: 0.85rem; cursor: pointer; transition: all 0.2s; display: flex; align-items: center; gap: 8px; text-decoration: none; }
        .btn-primary { background: var(--accent); color: #000; }
        .btn-secondary { background: var(--secondary); color: var(--text-primary); }
        .summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 40px; }
        .card { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 20px; padding: 24px; }
        .card-label { color: var(--text-secondary); font-size: 0.85rem; font-weight: 500; margin-bottom: 8px; display: block; }
        .card-value { font-size: 1.8rem; font-weight: 700; display: block; }
        .section-title { font-size: 1.25rem; font-weight: 700; margin: 40px 0 20px; display: flex; align-items: center; gap: 10px; }
        .section-title::after { content: ''; flex: 1; height: 1px; background: var(--card-border); }
        table { width: 100%; border-collapse: separate; border-spacing: 0; background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 16px; overflow: hidden; }
        th { text-align: left; padding: 16px 24px; background: rgba(255,255,255,0.02); color: var(--text-secondary); font-size: 0.75rem; text-transform: uppercase; }
        td { padding: 16px 24px; border-top: 1px solid var(--card-border); font-size: 0.9rem; }
        .bank-logo { width: 28px; height: 28px; border-radius: 6px; background: #fff; padding: 2px; object-fit: contain; }
        .badge { padding: 4px 8px; border-radius: 6px; font-size: 0.65rem; font-weight: 700; text-transform: uppercase; }
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
                <div style="width: 48px; height: 48px; background: linear-gradient(135deg, var(--accent), #818cf8); border-radius: 12px; display: flex; align-items: center; justify-content: center; font-weight: 700;">{{ me.firstname[0] }}</div>
                <div><div style="font-weight: 700;">{{ me.fullname }}</div><div style="color: var(--text-secondary); font-size: 0.8rem;">{{ me.email }}</div></div>
            </div>
            <div class="btn-group">
                <a href="/download" class="btn btn-secondary">💾 JSON</a>
                <button id="updateBtn" class="btn btn-primary" onclick="triggerUpdate()"><span class="spinner"></span><span class="icon">🔄</span><span id="btnText">Synchroniser</span></button>
                <div style="text-align: right; margin-left: 10px;"><div style="color: var(--text-secondary); font-size: 0.7rem;">Dernière Sync</div><div style="font-weight: 600; font-size: 0.85rem;">{{ timestamp }}</div></div>
            </div>
        </header>

        <div class="summary-grid">
            <div class="card"><span class="card-label">Patrimoine Global</span><span class="card-value">{{ "{:,.2f}".format(total_wealth) }} €</span></div>
            <div class="card"><span class="card-label">Revenus Mensuels</span><span class="card-value">{{ "{:,.0f}".format(me.income.salary) }} €</span></div>
            <div class="card"><span class="card-label">Capacité d'Épargne</span><span class="card-value">{{ "{:,.0f}".format(me.income.salary - me.income.expenses) }} €</span></div>
        </div>

        <div class="section-title">Tous vos Actifs</div>
        <table>
            <thead><tr><th>Actif / Institution</th><th>Catégorie</th><th>Valeur</th><th>Plus-value</th><th>Dernière Sync</th></tr></thead>
            <tbody>
                {% for acc in accounts %}
                <tr>
                    <td>
                        <div style="display: flex; align-items: center; gap: 12px;">
                            <img src="{{ acc.logo }}" class="bank-logo" onerror="this.src='https://finary.com/favicon.ico'">
                            <div><div style="font-weight: 600;">{{ acc.name }}</div><div style="font-size: 0.75rem; color: var(--text-secondary);">{{ acc.institution }}</div></div>
                        </div>
                    </td>
                    <td><span class="badge" style="background: rgba(56,189,248,0.1); color: var(--accent);">{{ acc.type }}</span></td>
                    <td style="font-weight: 700;">{{ "{:,.2f}".format(acc.balance) }} €</td>
                    <td class="{{ 'positive' if acc.upnl >= 0 else 'negative' }}">{{ "+" if acc.upnl >= 0 }}{{ "{:,.2f}".format(acc.upnl) }} €<div style="font-size: 0.7rem;">{{ "{:.2f}".format(acc.upnl_percent) }}%</div></td>
                    <td style="color: var(--text-secondary); font-size: 0.8rem;">{{ acc.last_sync }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    <script>
        function triggerUpdate() {
            const btn = document.getElementById('updateBtn'); btn.disabled = true; btn.classList.add('updating');
            fetch('/update', { method: 'POST' }).then(r => r.json()).then(d => { if (d.status === 'success') setTimeout(() => window.location.reload(), 3000); else alert(d.message); });
        }
    </script>
</body>
</html>
"""

def format_date(date_str):
    if not date_str: return "Inconnue"
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y %H:%M")
    except: return date_str

def get_financial_data():
    try:
        files = [f for f in os.listdir(DATA_DIR) if f.endswith(".json")]
        if not files: return None
        latest_file = max(files, key=lambda x: os.path.getmtime(os.path.join(DATA_DIR, x)))
        with open(os.path.join(DATA_DIR, latest_file), "r", encoding="utf-8") as f:
            raw = json.load(f)
        
        me_raw = raw.get("me", {}).get("result", {})
        summary = raw.get("portfolio_summary", {})
        categories = summary.get("categories", {})
        
        accounts = []
        
        # Flatten all categories into a single list
        for cat_name, cat_content in categories.items():
            # Investments/Accounts
            for acc in cat_content.get("accounts", []):
                accounts.append({
                    "name": acc.get("display_name") or acc.get("name"),
                    "institution": acc.get("bank", {}).get("name", "Manuel"),
                    "logo": acc.get("logo_url"),
                    "balance": acc.get("balance", 0),
                    "upnl": acc.get("upnl", 0),
                    "upnl_percent": acc.get("current_upnl_percent", 0),
                    "type": cat_name.replace("_", " ").title(),
                    "last_sync": format_date(acc.get("last_sync_at"))
                })
            # Cryptos
            for cry in cat_content.get("cryptos", []):
                accounts.append({
                    "name": cry.get("quantity", 0), # Simplified for crypto
                    "institution": cry.get("name"),
                    "logo": cry.get("logo_url"),
                    "balance": cry.get("balance", 0),
                    "upnl": cry.get("upnl", 0),
                    "upnl_percent": cry.get("upnl_percent", 0),
                    "type": "Crypto",
                    "last_sync": "N/A"
                })
            # Fonds Euro (Linxea etc)
            for fe in cat_content.get("fonds_euro", []):
                accounts.append({
                    "name": fe.get("display_name") or fe.get("name"),
                    "institution": fe.get("bank", {}).get("name", "Assurance Vie"),
                    "logo": fe.get("logo_url"),
                    "balance": fe.get("balance", 0),
                    "upnl": fe.get("upnl", 0),
                    "upnl_percent": fe.get("upnl_percent", 0),
                    "type": "Assurance Vie",
                    "last_sync": format_date(fe.get("last_sync_at"))
                })
            # SCPI
            for scpi in cat_content.get("scpis", []):
                accounts.append({
                    "name": scpi.get("name"),
                    "institution": "SCPI",
                    "logo": "",
                    "balance": scpi.get("balance", 0),
                    "upnl": scpi.get("upnl", 0),
                    "upnl_percent": scpi.get("upnl_percent", 0),
                    "type": "SCPI",
                    "last_sync": "N/A"
                })

        return {
            "timestamp": format_date(raw.get("timestamp")),
            "me": {
                "firstname": me_raw.get("firstname", "Utilisateur"),
                "lastname": me_raw.get("lastname", ""),
                "fullname": me_raw.get("fullname", "Utilisateur Finary"),
                "email": me_raw.get("email", ""),
                "income": {
                    "salary": me_raw.get("investor_profile", {}).get("monthly_salary", 0),
                    "expenses": me_raw.get("investor_profile", {}).get("monthly_expenses", 0),
                }
            },
            "total_wealth": summary.get("total_amount", 0),
            "accounts": accounts
        }
    except Exception as e:
        logging.error(f"Error parsing data: {e}")
        return None

@app.route("/")
def index():
    data = get_financial_data()
    if not data: return "<h1>En attente...</h1>"
    return render_template_string(HTML_TEMPLATE, **data)

@app.route("/update", methods=["POST"])
def update():
    global is_updating
    if is_updating: return jsonify({"status": "error", "message": "En cours"}), 400
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
