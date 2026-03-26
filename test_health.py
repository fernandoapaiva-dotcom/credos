import requests
import json

def test():
    base = 'http://127.0.0.1:8001'
    try:
        r = requests.get(base)
        print(f"Root Content: {r.text}")
        
        headers = {'x-company-cnpj': '11504286000169'}
        r2 = requests.get(f"{base}/api/crm/clients", headers=headers)
        print(f"Clients: {r2.status_code}")
        if r2.status_code == 200:
            count = len(r2.json().get('clients', []))
            print(f"Clients Count: {count}")
            
    except Exception as e:
        print(f"Error -> {e}")

if __name__ == '__main__':
    test()
