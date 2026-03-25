from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
import bcrypt
from src.database import listar_usuarios, criar_usuario, excluir_usuario, atualizar_usuario_db

router = APIRouter()

class UserCreate(BaseModel):
    login: str
    password: str
    nome_completo: str
    perfil: str = "operador"
    foto_b64: Optional[str] = None

class UserUpdate(BaseModel):
    nome_completo: Optional[str] = None
    perfil: Optional[str] = None
    password: Optional[str] = None
    foto_b64: Optional[str] = None

@router.get("/")
def get_users():
    users = listar_usuarios()
    # Remove password from response for security
    for u in users:
        if "password" in u:
            del u["password"]
    return {"users": users}

@router.post("/")
def add_user(user: UserCreate):
    # Hash password
    hashed = bcrypt.hashpw(user.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    sucesso, msg = criar_usuario(user.login, hashed, user.nome_completo, user.perfil, user.foto_b64)
    if sucesso:
        return {"message": msg, "success": True}
    else:
        raise HTTPException(status_code=400, detail=msg)

@router.delete("/{login}")
def remove_user(login: str):
    if login == 'admin@credos.com' or login == 'fernando':
         raise HTTPException(status_code=400, detail="Não é possível excluir usuários mestres.")
         
    if excluir_usuario(login):
        return {"success": True, "message": "Usuário excluído."}
    else:
        raise HTTPException(status_code=400, detail="Erro ao excluir usuário.")

@router.patch("/{login}")
def update_user(login: str, updates: UserUpdate):
    hashed_pwd = None
    if updates.password:
        hashed_pwd = bcrypt.hashpw(updates.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    if atualizar_usuario_db(login, updates.nome_completo, updates.perfil, hashed_pwd, updates.foto_b64):
        return {"success": True, "message": "Usuário atualizado."}
    else:
        raise HTTPException(status_code=400, detail="Erro ao atualizar usuário.")
