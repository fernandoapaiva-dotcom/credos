import json
import os
from datetime import datetime

DATABASE_DIR = os.getenv("DATABASE_DIR", "/app/data")
CONTEXT_FILE = os.path.join(DATABASE_DIR, "group_context_history.json")

def salvar_mensagem_contexto(group_jid, role, text):
    """
    Salva uma mensagem no histórico de contexto do grupo.
    role: 'user' ou 'model'
    """
    try:
        history = {}
        if os.path.exists(CONTEXT_FILE):
            try:
                with open(CONTEXT_FILE, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            except: history = {}
            
        if group_jid not in history:
            history[group_jid] = []
            
        history[group_jid].append({
            "role": role,
            "parts": [{"text": text}],
            "timestamp": datetime.now().isoformat()
        })
        
        # Mantém apenas as últimas 10 mensagens por grupo para não estourar o prompt
        history[group_jid] = history[group_jid][-10:]
        
        with open(CONTEXT_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
            
    except Exception as e:
        print(f"⚠️ Erro ao salvar contexto do grupo: {e}")

def obter_contexto_grupo(group_jid):
    """Retorna o histórico formatado para o Gemini."""
    try:
        if not os.path.exists(CONTEXT_FILE):
            return []
            
        with open(CONTEXT_FILE, 'r', encoding='utf-8') as f:
            history = json.load(f)
            
        return history.get(group_jid, [])
    except:
        return []

def limpar_contexto_grupo(group_jid):
    """Limpa o histórico de um grupo (ex: após comando concluído)."""
    try:
        if not os.path.exists(CONTEXT_FILE): return
        
        with open(CONTEXT_FILE, 'r', encoding='utf-8') as f:
            history = json.load(f)
            
        if group_jid in history:
            del history[group_jid]
            with open(CONTEXT_FILE, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
    except: pass
