import requests
import base64
import os

def get_qr():
    url = "http://localhost:8080"
    apikey = "42a24fa6-403d-4c7b-b30a-9359e9a4f783"
    instance = "54804458000122"
    
    endpoint = f"{url}/instance/connect/{instance}"
    headers = {"apikey": apikey}
    
    try:
        r = requests.get(endpoint, headers=headers, timeout=30)
        print(f"Status API: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            # On newer versions it might be in 'base64' directly or inside 'qrcode'
            qr_base64 = data.get('base64') or data.get('qrcode', {}).get('base64')
            
            if qr_base64:
                # Remove header if exists
                if "," in qr_base64:
                    qr_base64 = qr_base64.split(",")[1]
                
                img_data = base64.b64decode(qr_base64)
                with open("qrcode_dauto.png", "wb") as f:
                    f.write(img_data)
                print("QR Code salvo em qrcode_dauto.png")
            else:
                print(f"Erro: QR Code nao encontrado na resposta: {r.text}")
        else:
            print(f"Erro na API: {r.text}")
    except Exception as e:
        print(f"Falha ao conectar: {e}")

if __name__ == "__main__":
    get_qr()
