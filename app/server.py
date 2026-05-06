import os
import json
import logging
from flask import Flask, render_template_string, jsonify

app = Flask(__name__)
DATA_DIR = os.getenv("DATA_DIR", "/app/data")

# Premium Financial Dashboard Template
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
            --accent-glow: rgba(56, 189, 248, 0.2);
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
            transition: transform 0.2s, border-color 0.2s;
        }
        .card:hover {
            border-color: var(--accent);
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
            letter-spacing: 0.05em;
        }
        td {
            padding: 16px 24px;
            border-top: 1px solid var(--card-border);
            font-size: 0.9rem;
        }
        tr:hover td {
            background: rgba(255,255,255,0.01);
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
        .footer {
            margin-top: 60px;
            text-align: center;
            color: var(--text-secondary);
            font-size: 0.8rem;
        }
        .badge {
            padding: 4px 8px;
            border-radius: 6px;
            font-size: 0.7rem;
            font-weight: 700;
            text-transform: uppercase;
            background: var(--card-border);
        }
        .badge-plus { background: #f59e0b; color: #000; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="user-profile">
                <div class="avatar">{{ me.firstname[0] }}{{ me.lastname[0] }}</div>
                <div>
                    <div style="font-weight: 700; font-size: 1.1rem;">{{ me.fullname }}</div>
                    <div style="color: var(--text-secondary); font-size: 0.85rem;">{{ me.email }} <span class="badge badge-plus">{{ me.subscription }}</span></div>
                </div>
            </div>
            <div style="text-align: right;">
                <div style="color: var(--text-secondary); font-size: 0.75rem;">Dernière mise à jour</div>
                <div style="font-weight: 600;">{{ timestamp }}</div>
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

        <div class="footer">
            Généré avec ❤️ par Finary Downloader • Données sécurisées
        </div>
    </div>
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
        
        # Extraction sélective des données financières
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
                "subscription": me_raw.get("subscription_status", "free"),
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
        logging.error(f"Error parsing financial data: {e}")
        return None

@app.route("/")
def index():
    data = get_financial_data()
    if not data:
        return "<h1>En attente de données...</h1><p>Le premier téléchargement est en cours ou a échoué.</p>"
    return render_template_string(HTML_TEMPLATE, **data)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
