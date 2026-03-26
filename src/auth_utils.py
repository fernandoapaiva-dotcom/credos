import os
import datetime
from supabase import create_client, Client
from src.database import conectar

# --- SUPABASE CONFIG ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

def get_supabase_client() -> Client:
    if SUPABASE_URL and SUPABASE_ANON_KEY:
        return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    return None

def verificar_sso_token(sso_token: str):
    """
    Valida um token SSO no Supabase e busca o usuário local correspondente.
    Retorna (sucesso, dados_usuario, mensagem)
    """
    supabase = get_supabase_client()
    if not supabase:
        return False, None, "Configuração de SSO ausente no servidor (Supabase URL/Key)."

    try:
        # 1. Validar token no Supabase: Deve existir, ser atual e não estar usado
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
        
        res = supabase.table("sso_tokens") \
            .select("user_email") \
            .eq("id", sso_token) \
            .gt("expires_at", now_utc) \
            .is_("used_at", "null") \
            .execute()
        
        if not res.data:
            return False, None, "Token SSO inválido, expirado ou já utilizado."
        
        user_email = res.data[0]["user_email"]
        
        # 2. Marcar como utilizado para evitar reuso
        used_at = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
        supabase.table("sso_tokens").update({"used_at": used_at}).eq("id", sso_token).execute()
        
        # 3. Buscar usuário no SQLite local do Credos
        conn = conectar() 
        query = "SELECT nome_completo, perfil, foto_b64 FROM usuarios WHERE login=?"
        u_res = conn.cursor().execute(query, (user_email,)).fetchone()
        conn.close()
        
        if not u_res:
            return False, None, f"O e-mail '{user_email}' está no Hub mas não está cadastrado no Credos."
            
        nome_completo, perfil, foto_b64 = u_res
        
        user_data = {
            "username": user_email,
            "nome_completo": nome_completo,
            "perfil": perfil,
            "foto_b64": foto_b64
        }
        
        return True, user_data, "Login SSO realizado com sucesso."

    except Exception as e:
        return False, None, f"Erro no processamento do SSO: {str(e)}"
