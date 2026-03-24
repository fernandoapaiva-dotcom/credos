from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from typing import Optional
from src.database import conectar
import jwt
import datetime

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
        query = "SELECT password, nome_completo, perfil, foto_b64 FROM usuarios WHERE login=?"
        res = conn.cursor().execute(query, (request.username,)).fetchone()
        conn.close()
        
        if res:
            hashed_password, nome_completo, perfil, foto_b64 = res
            
            # Verificamos a senha
            if bcrypt.checkpw(request.password.encode('utf-8'), hashed_password.encode('utf-8')):
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
