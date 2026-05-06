import os
import json
import logging
import threading
from flask import Flask, render_template_string, jsonify, redirect, url_for
from finary_client import FinaryClient

app = Flask(__name__)
DATA_DIR = os.getenv("DATA_DIR", "/app/data")
FINARY_EMAIL = os.getenv("FINARY_EMAIL")
FINARY_PASSWORD = os.getenv("FINARY_PASSWORD")
FINARY_OTP_SECRET = os.getenv("FINARY_OTP_SECRET")

# Flag to prevent multiple simultaneous updates
is_updating = False

# Premium Financial Dashboard Template with Update Button
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
            --bg: #030712;
            --card-bg: #111827;
            --card-border: #1f2937;
            --accent: #38bdf8;
            --accent-hover: #0ea5e9;
            --success: #10b981;
            --danger: #ef4444;
            --text-primary: #f9fafb;
            --text-secondary: #9ca3af;
        }
        body {
            font-family: 'Plus Jakarta Sans', sans-serif;
            background-color: var(--bg);
            color: var(--text-primary);
            margin: 0;
            padding: 0;
            -webkit-font-smoothing: antialiased;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 40px 20px;
        }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 40px;
        }
        .user-profile {
            display: flex;
            align-items: center;
            gap: 15px;
        }
        .avatar {
            width: 48px;
            height: 48px;
            background: linear-gradient(135deg, var(--accent), #818cf8);
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 1.2rem;
        }
        .summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }
        .card {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 20px;
            padding: 24px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }
        .card-label {
            color: var(--text-secondary);
            font-size: 0.85rem;
            font-weight: 500;
            margin-bottom: 8px;
            display: block;
        }
        .card-value {
            font-size: 1.8rem;
            font-weight: 700;
            display: block;
        }
        .card-evolution {
            font-size: 0.9rem;
            margin-top: 8px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 4px;
        }
        .positive { color: var(--success); }
        .negative { color: var(--danger); }

        .btn-update {
            background: var(--accent);
            color: #000;
            border: none;
            padding: 10px 20px;
            border-radius: 10px;
            font-weight: 700;
            font-size: 0.9rem;
            cursor: pointer;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            gap: 8px;
            text-decoration: none;
        }
        .btn-update:hover {
            background: var(--accent-hover);
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(56, 189, 248, 0.3);
        }
        .btn-update:disabled {
            background: var(--card-border);
            color: var(--text-secondary);
            cursor: not-allowed;
            transform: none;
            box-shadow: none;
        }

        .section-title {
            font-size: 1.25rem;
            font-weight: 700;
            margin: 40px 0 20px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .section-title::after {
            content: '';
            flex: 1;
            height: 1px;
            background: var(--card-border);
        }

        table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            overflow: hidden;
        }
        th {
            text-align: left;
            padding: 16px 24px;
            background: rgba(255,255,255,0.02);
            color: var(--text-secondary);
            font-weight: 600;
            font-size: 0.75rem;
            text-transform: uppercase;
        }
        td {
            padding: 16px 24px;
            border-top: 1px solid var(--card-border);
            font-size: 0.9rem;
        }
        .bank-info {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .bank-logo {
            width: 32px;
            height: 32px;
            border-radius: 8px;
            background: #fff;
            padding: 2px;
            object-fit: contain;
        }
        .badge {
            padding: 4px 8px;
            border-radius: 6px;
            font-size: 0.7rem;
            font-weight: 700;
            text-transform: uppercase;
            background: var(--card-border);
        }
        
        /* Spinner */
        .spinner {
            width: 16px;
            height: 16px;
            border: 2px solid rgba(0,0,0,0.3);
            border-top: 2px solid #000;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            display: none;
        }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        
        .updating .spinner { display: block; }
        .updating .icon { display: none; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="user-profile">
                <div class="avatar">{{ me.firstname[0] }}{{ me.lastname[0] }}</div>
                <div>
                    <div style="font-weight: 700; font-size: 1.1rem;">{{ me.fullname }}</div>
                    <div style="color: var(--text-secondary); font-size: 0.85rem;">{{ me.email }}</div>
                </div>
            </div>
            <div style="display: flex; align-items: center; gap: 20px;">
                <button id="updateBtn" class="btn-update" onclick="triggerUpdate()">
                    <span class="spinner"></span>
                    <span class="icon">🔄</span>
                    <span id="btnText">Mettre à jour</span>
                </button>
                <div style="text-align: right;">
                    <div style="color: var(--text-secondary); font-size: 0.75rem;">Dernière snapshot</div>
                    <div style="font-weight: 600;">{{ timestamp }}</div>
                </div>
            </div>
        </header>

        <div class="summary-grid">
            <div class="card">
                <span class="card-label">Patrimoine Brut</span>
                <span class="card-value">{{ "{:,.2f}".format(portfolio.total.amount) }} €</span>
                <div class="card-evolution {{ 'positive' if portfolio.total.evolution >= 0 else 'negative' }}">
                    {{ "▲" if portfolio.total.evolution >= 0 else "▼" }} 
                    {{ "{:,.2f}".format(portfolio.total.evolution) }} € ({{ "{:.2f}".format(portfolio.total.evolution_percent) }}%)
                </div>
            </div>
            <div class="card">
                <span class="card-label">Revenus Mensuels</span>
                <span class="card-value">{{ "{:,.0f}".format(me.income.salary) }} €</span>
                <span class="card-label" style="margin-top: 10px;">Dépenses : {{ "{:,.0f}".format(me.income.expenses) }} €</span>
            </div>
            <div class="card">
                <span class="card-label">Taux d'Imposition</span>
                <span class="card-value">{{ me.income.tax_rate }} %</span>
                <span class="card-label" style="margin-top: 10px;">Âge : {{ me.age }} ans</span>
            </div>
        </div>

        <div class="section-title">Comptes & Institutions</div>
        <table>
            <thead>
                <tr>
                    <th>Institution / Compte</th>
                    <th>Type</th>
                    <th>Solde</th>
                    <th>Plus-value</th>
                    <th>Dernière Sync</th>
                </tr>
            </thead>
            <tbody>
                {% for acc in portfolio.accounts %}
                <tr>
                    <td>
                        <div class="bank-info">
                            <img src="{{ acc.logo }}" class="bank-logo" onerror="this.style.display='none'">
                            <div>
                                <div style="font-weight: 600;">{{ acc.name }}</div>
                                <div style="font-size: 0.75rem; color: var(--text-secondary);">{{ acc.bank_name }}</div>
                            </div>
                        </div>
                    </td>
                    <td><span class="badge">{{ acc.type }}</span></td>
                    <td style="font-weight: 700;">{{ "{:,.2f}".format(acc.balance) }} €</td>
                    <td class="{{ 'positive' if acc.upnl >= 0 else 'negative' }}">
                        {{ "+" if acc.upnl >= 0 }}{{ "{:,.2f}".format(acc.upnl) }} €
                        <div style="font-size: 0.75rem;">{{ "{:.2f}".format(acc.upnl_percent) }}%</div>
                    </td>
                    <td style="color: var(--text-secondary); font-size: 0.8rem;">{{ acc.last_sync }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>

    <script>
        function triggerUpdate() {
            const btn = document.getElementById('updateBtn');
            const btnText = document.getElementById('btnText');
            
            btn.disabled = true;
            btn.classList.add('updating');
            btnText.innerText = 'Mise à jour...';
            
            fetch('/update', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'success') {
                        setTimeout(() => {
                            window.location.reload();
                        }, 2000);
                    } else {
                        alert('Erreur : ' + data.message);
                        resetBtn();
                    }
                })
                .catch(err => {
                    alert('Erreur de connexion');
                    resetBtn();
                });
        }
        
        function resetBtn() {
            const btn = document.getElementById('updateBtn');
            const btnText = document.getElementById('btnText');
            btn.disabled = false;
            btn.classList.remove('updating');
            btnText.innerText = 'Mettre à jour';
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
    except:
        return date_str

def get_financial_data():
    try:
        files = [f for f in os.listdir(DATA_DIR) if f.endswith(".json")]
        if not files: return None
        
        latest_file = max(files, key=lambda x: os.path.getmtime(os.path.join(DATA_DIR, x)))
        with open(os.path.join(DATA_DIR, latest_file), "r", encoding="utf-8") as f:
            raw = json.load(f)
        
        me_raw = raw.get("me", {}).get("result", {})
        portfolio_raw = raw.get("portfolio", {}).get("result", {})
        
        data = {
            "timestamp": format_date(raw.get("timestamp")),
            "me": {
                "firstname": me_raw.get("firstname", "Utilisateur"),
                "lastname": me_raw.get("lastname", ""),
                "fullname": me_raw.get("fullname", "Utilisateur Finary"),
                "email": me_raw.get("email", ""),
                "age": me_raw.get("age", ""),
                "income": {
                    "salary": me_raw.get("investor_profile", {}).get("monthly_salary", 0),
                    "expenses": me_raw.get("investor_profile", {}).get("monthly_expenses", 0),
                    "tax_rate": me_raw.get("investor_profile", {}).get("income_tax_rate", 0),
                }
            },
            "portfolio": {
                "total": {
                    "amount": portfolio_raw.get("total", {}).get("amount", 0),
                    "evolution": portfolio_raw.get("total", {}).get("evolution", 0),
                    "evolution_percent": portfolio_raw.get("total", {}).get("evolution_percent", 0),
                },
                "accounts": []
            }
        }
        
        for acc in portfolio_raw.get("accounts", []):
            data["portfolio"]["accounts"].append({
                "name": acc.get("display_name") or acc.get("name"),
                "bank_name": acc.get("bank", {}).get("name", "Manuel"),
                "logo": acc.get("logo_url"),
                "balance": acc.get("balance", 0),
                "upnl": acc.get("upnl", 0),
                "upnl_percent": acc.get("current_upnl_percent", 0),
                "type": acc.get("bank_account_type", {}).get("display_name", "Autre"),
                "last_sync": format_date(acc.get("last_sync_at"))
            })
            
        return data
    except Exception as e:
        return None

@app.route("/")
def index():
    data = get_financial_data()
    if not data:
        return "<h1>En attente de données...</h1><p>Cliquez sur Mettre à jour pour lancer le premier snapshot.</p><form action='/update' method='POST'><button type='submit'>Lancer la première synchro</button></form>"
    return render_template_string(HTML_TEMPLATE, **data)

@app.route("/update", methods=["POST"])
def update():
    global is_updating
    if is_updating:
        return jsonify({"status": "error", "message": "Mise à jour déjà en cours"}), 400
    
    def run_update():
        global is_updating
        is_updating = True
        try:
            client = FinaryClient(FINARY_EMAIL, FINARY_PASSWORD, FINARY_OTP_SECRET)
            client.fetch_and_save(DATA_DIR)
        finally:
            is_updating = False

    thread = threading.Thread(target=run_update)
    thread.start()
    return jsonify({"status": "success", "message": "Mise à jour lancée"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
