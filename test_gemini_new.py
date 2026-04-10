import os
from google import genai
try:
    client = genai.Client(api_key='AIzaSyB5j_H_pvZ-cFaahzdCxvrqk0fgsWVfTJI')
    response = client.models.generate_content(model='gemini-2.5-flash', contents='Oi, mundo')
    print("RESPOSTA IA:", response.text)
except Exception as e:
    print("ERRO:", str(e))
