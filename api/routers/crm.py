from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import List, Optional
from src.database import listar_clientes_db, salvar_cliente_db, excluir_cliente_db, listar_titulos_por_cliente, atualizar_titulo_status_acao
import datetime
import sqlite3

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

router = APIRouter()

def get_cnpj(x_company_cnpj: str = Header(None)):
    if not x_company_cnpj:
        raise HTTPException(status_code=400, detail="CNPJ da empresa (X-Company-Cnpj) é obrigatório nos headers")
    return x_company_cnpj

class ClientModel(BaseModel):
    nome: str
    cnpj: str
    whatsapp: str
    email: str
    contato: str

class TitleStatusUpdate(BaseModel):
    status: str # "Aberto", "Pago", "Negociado", "Cartório", "Baixado"
    acao: str   # "Cobrar", "Pausar"
    data_promessa: Optional[str] = None # Para o caso de Negociado

@router.get("/clients")
def get_clients(x_company_cnpj: str = Header(...)):
    cnpj = get_cnpj(x_company_cnpj)
    clientes = listar_clientes_db(cnpj)
    return {"clients": clientes}

@router.post("/clients")
def save_client(client: ClientModel, x_company_cnpj: str = Header(...)):
    cnpj = get_cnpj(x_company_cnpj)
    salvar_cliente_db(cnpj, client.nome, client.cnpj, client.whatsapp, client.email, client.contato)
    return {"success": True, "message": "Cliente salvo com sucesso."}

@router.put("/clients/{id}")
def update_client(id: int, client: ClientModel, x_company_cnpj: str = Header(...)):
    cnpj = get_cnpj(x_company_cnpj)
    from src.database import conectar
    conn = conectar(cnpj)
    c = conn.cursor()
    try:
        c.execute("""
            UPDATE clientes 
            SET nome=?, cnpj=?, whatsapp=?, email=?, contato=?
            WHERE id=?
        """, (client.nome, client.cnpj, client.whatsapp, client.email, client.contato, id))
        conn.commit()
        return {"success": True, "message": "Cliente atualizado."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

@router.delete("/clients/{id}")
def delete_client(id: int, nome: str, x_company_cnpj: str = Header(...)):
    cnpj = get_cnpj(x_company_cnpj)
    excluir_cliente_db(cnpj, id, nome, "API User")
    return {"success": True, "message": "Cliente deletado."}

@router.get("/titles")
def get_all_titles(status: Optional[str] = None, x_company_cnpj: str = Header(...)):
    cnpj = get_cnpj(x_company_cnpj)
    from src.database import conectar
    conn = conectar(cnpj)
    conn.row_factory = dict_factory
    
    query = "SELECT * FROM titulos"
    params = []
    if status:
        query += " WHERE status = ?"
        params.append(status)
        
    res = conn.cursor().execute(query, params).fetchall()
    conn.close()
    return {"titles": res}

@router.get("/clients/{nome}/titles")
def get_client_titles(nome: str, x_company_cnpj: str = Header(...)):
    cnpj = get_cnpj(x_company_cnpj)
    titulos = listar_titulos_por_cliente(cnpj, nome)
    return {"titles": titulos}

@router.patch("/titles/{id_titulo}")
def update_title_status(id_titulo: int, update: TitleStatusUpdate, x_company_cnpj: str = Header(...)):
    cnpj = get_cnpj(x_company_cnpj)
    
    # Base user logic: The status changing logic.
    # Open -> Charge or Pause.
    # Paid -> Baixado (move).
    # Negotiated -> If data_promessa, it should be handled by a scheduler, but we record the status.
    novo_status = update.status
    nova_acao = update.acao
    
    # Se o status é pago, automaticamente podemos baixar.
    if novo_status == "Pago":
        novo_status = "Baixado"
        nova_acao = "Pausar"
    elif novo_status in ["Baixado", "Cancelado"]:
        nova_acao = "Pausar"
        
    atualizar_titulo_status_acao(cnpj, id_titulo, novo_status, nova_acao)
    return {"success": True, "message": f"Título atualizado para {novo_status} - {nova_acao}"}

@router.get("/dashboard-stats")
def get_dashboard_stats(x_company_cnpj: str = Header(...)):
    cnpj = get_cnpj(x_company_cnpj)
    from src.database import obter_stats_dashboard
    return obter_stats_dashboard(cnpj)

@router.post("/charge-all")
def charge_all_company(x_company_cnpj: str = Header(...)):
    cnpj = get_cnpj(x_company_cnpj)
    from src.worker import disparar_cobranca_automatica
    total = disparar_cobranca_automatica(forcar_execucao=True, cnpj_filtro=cnpj)
    return {"success": True, "total_envios": total}

@router.post("/preview-charge-all")
def preview_charge_all(x_company_cnpj: str = Header(...)):
    from src.manager import Manager
    mgr = Manager(get_cnpj(x_company_cnpj))
    resumo = mgr.prever_cobranca_coletiva()
    return {"success": True, "preview": resumo}

@router.post("/clients/{nome}/charge")
def charge_client(nome: str, x_company_cnpj: str = Header(...)):
    from src.manager import Manager
    mgr = Manager(get_cnpj(x_company_cnpj))
    return mgr.cobrar_cliente_especifico(nome)

@router.post("/titles/{id}/charge")
def charge_title(id: int, x_company_cnpj: str = Header(...)):
    from src.manager import Manager
    mgr = Manager(get_cnpj(x_company_cnpj))
    return mgr.cobrar_titulo_unico(id)

# ─── GESTÃO DE COMPROVANTES RECEBIDOS ─────────────────────────

@router.get("/vouchers")
def list_vouchers(x_company_cnpj: str = Header(...)):
    cnpj = get_cnpj(x_company_cnpj)
    from src.database import conectar
    conn = conectar(cnpj)
    conn.row_factory = dict_factory
    try:
        res = conn.cursor().execute(
            "SELECT * FROM comprovantes ORDER BY recebido_em DESC"
        ).fetchall()
        return {"vouchers": res}
    finally:
        conn.close()

@router.post("/vouchers/{id}/process")
async def process_voucher(id: int, acao: str, x_company_cnpj: str = Header(...)):
    """
    acao: 'confirmar' ou 'negar'
    Utiliza a mesma lógica do webhook para manter consistência.
    """
    cnpj = get_cnpj(x_company_cnpj)
    from api.routers.webhook import confirmar_pagamento
    await confirmar_pagamento(id, acao, cnpj)
    return {"success": True, "message": f"Comprovante {id} processado com ação: {acao}"}

# ─── GESTÃO DE CONVERSAS (WhatsApp) ─────────────────────────

@router.get("/conversations")
def list_conversations(x_company_cnpj: str = Header(...)):
    cnpj = get_cnpj(x_company_cnpj)
    from src.database import conectar
    conn = conectar(cnpj)
    conn.row_factory = dict_factory
    try:
        res = conn.cursor().execute(
            "SELECT id, numero_whatsapp, cliente_nome, estado, ultima_interacao, ultima_mensagem_enviada, history_json FROM webhook_sessions ORDER BY id DESC"
        ).fetchall()
        
        # Opcional: Processar JSON para não quebrar no frontend
        import json
        for row in res:
            try:
                row["history"] = json.loads(row["history_json"]) if row["history_json"] else []
            except Exception:
                row["history"] = []
            del row["history_json"]
            
        return {"conversations": res}
    finally:
        conn.close()
