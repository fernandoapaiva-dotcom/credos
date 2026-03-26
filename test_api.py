import requests
import traceback

try:
    # Let's craft a fake request to the internal DB layer instead to catch exactly where it errors
    login_data = {"username": "admin", "password": "123"}
    res_login = requests.post("http://localhost:8001/api/auth/login", json=login_data)
    if res_login.status_code == 200:
        token = res_login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        req_data = {
            "cliente": "Todos",
            "data_inicio": "2026-03-19",
            "data_fim": "2026-03-19",
            "tipo": "Aberto"
        }
        res_rep = requests.post("http://localhost:8001/api/reports/generate", json=req_data, headers=headers)
        print(f"Status: {res_rep.status_code}")
        print(f"Response: {res_rep.text[:200]}")
    else:
        print("Login failed:", res_login.status_code, res_login.text)
except Exception as e:
    traceback.print_exc()
