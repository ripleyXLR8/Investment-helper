import os
import json
import logging
from flask import Flask, render_template_string, jsonify

app = Flask(__name__)
DATA_DIR = os.getenv("DATA_DIR", "/app/data")

# Premium Dark Theme Dashboard
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Finary Data Viewer</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --text-color: #f8fafc;
            --accent-color: #38bdf8;
            --secondary-text: #94a3b8;
        }
        body {
            font-family: 'Inter', sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            margin: 0;
            padding: 20px;
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        .container {
            max-width: 1000px;
            width: 100%;
        }
        header {
            text-align: center;
            margin-bottom: 40px;
        }
        h1 {
            font-weight: 600;
            background: linear-gradient(to right, #38bdf8, #818cf8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-size: 2.5rem;
        }
        .card {
            background-color: var(--card-bg);
            border-radius: 16px;
            padding: 24px;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        .info {
            display: flex;
            justify-content: space-between;
            margin-bottom: 20px;
            font-size: 0.9rem;
            color: var(--secondary-text);
        }
        pre {
            background-color: #000;
            padding: 20px;
            border-radius: 8px;
            overflow-x: auto;
            font-size: 13px;
            line-height: 1.5;
            color: #d1d5db;
            border: 1px solid #334155;
        }
        .string { color: #10b981; }
        .number { color: #f59e0b; }
        .boolean { color: #818cf8; }
        .null { color: #ef4444; }
        .key { color: #38bdf8; }
        
        .footer {
            margin-top: 40px;
            font-size: 0.8rem;
            color: var(--secondary-text);
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Finary Data Explorer</h1>
            <p>Visualisation en temps réel de votre dernier snapshot financier</p>
        </header>

        <div class="card">
            <div class="info">
                <span>Dernier fichier : <strong>{{ filename }}</strong></span>
                <span>Horodatage : <strong>{{ timestamp }}</strong></span>
            </div>
            <pre id="json-viewer">{{ json_content }}</pre>
        </div>

        <div class="footer">
            Auto-généré par Finary Downloader • Docker Container
        </div>
    </div>

    <script>
        function syntaxHighlight(json) {
            if (typeof json != 'string') {
                json = JSON.stringify(json, undefined, 2);
            }
            json = json.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            return json.replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)/g, function (match) {
                var cls = 'number';
                if (/^"/.test(match)) {
                    if (/:$/.test(match)) {
                        cls = 'key';
                    } else {
                        cls = 'string';
                    }
                } else if (/true|false/.test(match)) {
                    cls = 'boolean';
                } else if (/null/.test(match)) {
                    cls = 'null';
                }
                return '<span class="' + cls + '">' + match + '</span>';
            });
        }
        
        const content = document.getElementById('json-viewer').textContent;
        const json = JSON.parse(content);
        document.getElementById('json-viewer').innerHTML = syntaxHighlight(json);
    </script>
</body>
</html>
"""

def get_latest_data():
    try:
        files = [f for f in os.listdir(DATA_DIR) if f.endswith(".json")]
        if not files:
            return None, None, {"message": "Aucune donnée disponible. Attendez le prochain téléchargement."}
        
        latest_file = max(files, key=lambda x: os.path.getmtime(os.path.join(DATA_DIR, x)))
        with open(os.path.join(DATA_DIR, latest_file), "r", encoding="utf-8") as f:
            content = json.load(f)
        
        return latest_file, content.get("timestamp", "Inconnu"), content
    except Exception as e:
        return "Erreur", str(e), {"error": str(e)}

@app.route("/")
def index():
    filename, timestamp, content = get_latest_data()
    return render_template_string(
        HTML_TEMPLATE, 
        filename=filename, 
        timestamp=timestamp, 
        json_content=json.dumps(content, indent=4)
    )

@app.route("/api/latest")
def api_latest():
    _, _, content = get_latest_data()
    return jsonify(content)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
