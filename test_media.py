import requests, base64

# Simple test PDF base64 (just a dummy PDF)
b64 = "JVBERi0xLjcKCjEgMCBvYmogICUgZW50cnkgcG9pbnQKPDwKICAvVHlwZSAvQ2F0YWxvZwogIC9QYWdlcyAyIDAgUgo+PgplbmRvYmoKCjIgMCBvYmoKPDwKICAvVHlwZSAvUGFnZXMKICAvTWVkaWFCb3ggWyAwIDAgMjAwIDIwMCBdCiAgL0NvdW50IDEKICAvS2lkcyBbIDMgMCBSIF0KPj4KZW5kb2JqCgozIDAgb2JqCjwwKCAgL1R5cGUgL1BhZ2UKICAvUGFyZW50IDIgMCBSCiAgL1Jlc291cmNlcyA8PAogICAgL0ZvbnQgPDwKICAgICAgL0YxIDQgMCBSCj4+CiAgPj4KICAvQ29udGVudHMgNSAwIFIKPj4KZW5kb2JqCgo0IDAgb2JqCjw8CiAgL1R5cGUgL0ZvbnQKICAvU3VidHlwZSAvVHlwZTEKICAvQmFzZUZvbnQgL1RpbWVzLVJvbWFuCj4+CmVuZG9iagoKNSAwIG9iago8PAogIC9MZW5ndGggMzYKPj4Kc3RyZWFtCkJUCjcwIDUwIFRECi9GMSAxMiBUZgooSGVsbG8sIHdvcmxkISkgVGoKRVQKZW5kc3RyZWFtCmVuZG9iagoKeHJlZgowIDYKMDAwMDAwMDAwMCA2NTUzNSBmIAowMDAwMDAwMDEwIDAwMDAwIG4gCjAwMDAwMDAwNjcgMDAwMDAgbiAKMDAwMDAwMDE1MCAwMDAwMCBuIAowMDAwMDAwMjc5IDAwMDAwIG4gCjAwMDAwMDAzNjMgMDAwMDAgbiAKdHJhaWxlcgo8PAogIC9TaXplIDYKICAvUm9vdCAxIDAgUgo+PgpzdGFydHhyZWYKNDQ5CiUlRU9GCg=="

url = "http://localhost:8080/message/sendMedia/001_Test"
headers = {"apikey": "42a24fa6-403d-4c7b-b30a-9359e9a4f783", "Content-Type": "application/json"}
target = "5561998334833@s.whatsapp.net"

variants = [
    {
        "name": "V1 (Root Media)",
        "payload": {
            "number": target,
            "mediatype": "document",
            "fileName": "test.pdf",
            "media": b64
        }
    },
    {
        "name": "V2 (options + mediaMessage)",
        "payload": {
            "number": target,
            "options": {"delay": 1200, "presence": "document"},
            "mediaMessage": {
                "mediatype": "document",
                "fileName": "test.pdf",
                "media": b64
            }
        }
    },
    {
        "name": "V3 (mediaMessage only)",
        "payload": {
            "number": target,
            "mediaMessage": {
                "mediatype": "document",
                "fileName": "test.pdf",
                "media": b64
            }
        }
    }
]

for v in variants:
    print(f"Testing {v['name']}...")
    try:
        r = requests.post(url, json=v['payload'], headers=headers)
        print(r.status_code, r.text)
    except Exception as e:
        print("Erro:", e)
