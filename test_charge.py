import requests
import json

def test_charge():
    base = 'http://127.0.0.1:8001'
    headers = {'x-company-cnpj': '11504286000169'}
    
    # 1. Get a title ID
    r = requests.get(f"{base}/api/crm/titles", headers=headers)
    titles = r.json().get('titles', [])
    if not titles:
        print("No titles found.")
        return
        
    tid = titles[0]['id']
    print(f"Testing Charge for Title ID: {tid}")
    
    # 2. Trigger charge
    r2 = requests.post(f"{base}/api/crm/titles/{tid}/charge", headers=headers)
    print(f"Status: {r2.status_code}")
    print(f"Response: {r2.text}")

if __name__ == '__main__':
    test_charge()
