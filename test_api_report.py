import requests

url = "http://localhost:8001/api/reports/generate"
headers = {
    "x-company-cnpj": "11504286000169",
    "Content-Type": "application/json"
}
payload = {
    "cliente": "Todos",
    "data_inicio": "2026-04-09",
    "data_fim": "2026-04-09",
    "tipo": "Historico"
}

try:
    resp = requests.post(url, json=payload, headers=headers)
    print("STATUS:", resp.status_code)
    print("HEADERS:", resp.headers)
    if resp.status_code != 200:
        print("ERROR:", resp.text)
    else:
        print("OK: Received file of length", len(resp.content))
except Exception as e:
    print("EXCEPTION:", e)
