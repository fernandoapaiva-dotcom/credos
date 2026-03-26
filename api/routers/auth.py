from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from typing import Optional
from src.database import conectar
import jwt
import datetime
import os
from supabase import create_client, Client

# --- SUPABASE CONFIG ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

if SUPABASE_URL and SUPABASE_ANON_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
else:
    supabase = None

router = APIRouter()

SECRET_KEY = "credos_super_secret_key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 # 24 horas

class LoginRequest(BaseModel):
    username: str
    password: str

class ForgotPasswordRequest(BaseModel):
    email: str

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

@router.post("/login")
def login(request: LoginRequest):
    import bcrypt
    try:
        conn = conectar() 
        # Buscamos a senha hasheada no banco
        print(f"DEBUG: Tentativa de login para: {request.username}")
        query = "SELECT password, nome_completo, perfil, foto_b64 FROM usuarios WHERE login=?"
        res = conn.cursor().execute(query, (request.username,)).fetchone()
        conn.close()
        
        if res:
            hashed_password, nome_completo, perfil, foto_b64 = res
            print(f"DEBUG: Usuário {request.username} encontrado no banco.")
            
            # Verificamos a senha
            try:
                match = bcrypt.checkpw(request.password.encode('utf-8'), hashed_password.encode('utf-8'))
                print(f"DEBUG: Resultado bcrypt.checkpw: {match}")
            except Exception as be:
                print(f"DEBUG: Erro no bcrypt (provável senha plano): {be}")
                # Fallback para texto plano se o banco tiver a senha sem hash
                match = (request.password == hashed_password)
                print(f"DEBUG: Resultado fallback texto plano: {match}")
                
            if match:
                token = create_access_token(data={"sub": request.username, "nome": nome_completo, "perfil": perfil})
                return {
                    "access_token": token,
                    "token_type": "bearer",
                    "user": {
                        "username": request.username,
                        "nome_completo": nome_completo,
                        "perfil": perfil,
                        "foto_b64": foto_b64
                    }
                }
        else:
            print(f"DEBUG: Usuário {request.username} NÃO encontrado no banco.")
        
        # Se cair aqui, usuário não existe ou senha errada
        raise HTTPException(status_code=401, detail="Usuário ou senha incorretos.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno no servidor: {str(e)}")

@router.post("/forgot-password")
def forgot_password(request: ForgotPasswordRequest):
    # A logica do forgot password pedida pelo usuario.
    # Por enquanto, só vamos checar se o usuário existe, e criar uma nova senha generica.
    conn = conectar()
    user = conn.cursor().execute("SELECT login FROM usuarios WHERE login=?", (request.email,)).fetchone()
    
    if not user:
        conn.close()
        # Não retornar erro exato por segurança, mas o UI espera algo
        return {"message": "Se o email estiver cadastrado, um link de recuperação será enviado."}
    
    # Aqui entraria o código real de envio de email. 
    # Para o teste / MVP, podemos apenas gerar um token ou setar uma senha 123456...
    # O usuario pediu: "botão de esqueceu a senha para enviar um link de reset para o email cadastrado"
    # Vamos gerar um token provisorio.
    reset_token = create_access_token(data={"sub": request.email, "type": "reset"})
    conn.close()
    
    # NOTA: O envio de email de SMTP centralizado não existe claro, cada empresa tem o seu,
    # então usaremos um placeholder no terminal ou log.
    print(f"EMAIL SIMULADO PARA: {request.email} - LINK DE RESET: http://localhost:5173/reset-password?token={reset_token}")
    
    return {"message": "Se o email estiver cadastrado, as instruções foram enviadas."}

from src.auth_utils import verificar_sso_token

@router.get("/sso-login")
def sso_login(sso_token: str):
    print(f"DEBUG SSO: Iniciando login para o token: {sso_token}")
    
    sucesso, user_data, msg = verificar_sso_token(sso_token)
    
    if not sucesso:
        print(f"DEBUG SSO: {msg}")
        if "Configuração" in msg:
            raise HTTPException(status_code=500, detail=msg)
        elif "não está cadastrado" in msg:
            raise HTTPException(status_code=404, detail=msg)
        else:
            raise HTTPException(status_code=401, detail=msg)
    
    # Gerar Token JWT do Credos (sucesso!)
    print(f"DEBUG SSO: Login efetuado com sucesso para {user_data['nome_completo']}")
    token = create_access_token(data={
        "sub": user_data["username"], 
        "nome": user_data["nome_completo"], 
        "perfil": user_data["perfil"]
    })
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user_data
    }
