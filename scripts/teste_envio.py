import sys
import os

# Adiciona a raiz do projeto ao caminho de busca do Python
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.messenger import Messenger

m = Messenger()
# ... resto do seu código

from src.messenger import Messenger

m = Messenger()
status, msg = m.enviar_whatsapp("5561998334833", "Teste de conexão Credos!") # Coloque seu número com DDD
print(f"Status: {status} | Resposta: {msg}")