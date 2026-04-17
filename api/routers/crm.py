from fastapi import APIRouter, HTTPException, Header, Response
from pydantic import BaseModel
from typing import List, Optional
from src.database import listar_clientes_db, salvar_cliente_db, excluir_cliente_db, listar_titulos_por_cliente, atualizar_titulo_status_acao, conectar
import datetime
import sqlite3
import os
import base64

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

class ChargePayload(BaseModel):
    canais: List[str] = ["whatsapp", "email"]

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
        
        # Sincroniza com o banco global para evitar que o listar_clientes_db sobrescreva o dado local com o global antigo
        from src.database import upsert_contato_global
        upsert_contato_global(client.cnpj, client.whatsapp, client.email, client.contato)
        
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
def charge_all_company(payload: Optional[ChargePayload] = None, x_company_cnpj: str = Header(...)):
    cnpj = get_cnpj(x_company_cnpj)
    from src.worker import disparar_cobranca_automatica
    canais = payload.canais if payload else ["whatsapp", "email"]
    total = disparar_cobranca_automatica(forcar_execucao=True, cnpj_filtro=cnpj, canais_selecionados=canais)
    return {"success": True, "total_envios": total}

@router.post("/preview-charge-all")
def preview_charge_all(x_company_cnpj: str = Header(...)):
    from src.manager import Manager
    mgr = Manager(get_cnpj(x_company_cnpj))
    resumo = mgr.prever_cobranca_coletiva()
    return {"success": True, "preview": resumo}

@router.post("/clients/{nome}/charge")
def charge_client(nome: str, payload: Optional[ChargePayload] = None, x_company_cnpj: str = Header(...)):
    from src.manager import Manager
    mgr = Manager(get_cnpj(x_company_cnpj))
    canais = payload.canais if payload else ["whatsapp", "email"]
    return mgr.cobrar_cliente_especifico(nome, canais_selecionados=canais)

@router.post("/titles/{id}/charge")
def charge_title(id: int, payload: Optional[ChargePayload] = None, x_company_cnpj: str = Header(...)):
    from src.manager import Manager
    mgr = Manager(get_cnpj(x_company_cnpj))
    canais = payload.canais if payload else ["whatsapp", "email"]
    return mgr.cobrar_titulo_unico(id, canais_selecionados=canais)

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

# ─── DOCUMENTOS FISCAIS (NFe/NFS/Boleto) ──────────────────────────

@router.get("/titles/{numero_nf}/documentos")
def get_title_documents(numero_nf: str, pagador: str, x_company_cnpj: str = Header(...)):
    """
    Retorna a lista de documentos fiscais (PDF/XML) indexados para uma NF e pagador específicos.
    Busca tanto pelo número da NF quanto pelo CNPJ do cliente.
    """
    cnpj = get_cnpj(x_company_cnpj)
    conn = conectar(cnpj)
    conn.row_factory = dict_factory
    try:
        # 1. Busca o CNPJ do cliente pelo nome do pagador
        cli = conn.cursor().execute(
            "SELECT cnpj FROM clientes WHERE trim(nome) = ?", (pagador.strip(),)
        ).fetchone()
        cnpj_cliente = ""
        if cli and cli.get('cnpj'):
            cnpj_cliente = str(cli['cnpj']).replace('.','').replace('/','').replace('-','').strip()

        # 2. Busca documentos por NF no banco
        nf_str = str(numero_nf).lstrip('0')
        docs = conn.cursor().execute("""
            SELECT id, num_nf, tipo, emissao, valor, fpath_local, created_at
            FROM documentos_fiscais
            WHERE (num_nf = ? OR num_nf LIKE ?)
            ORDER BY created_at DESC
        """, (nf_str, f"%{nf_str}%")).fetchall()

        resultado = []
        for d in docs:
            fpath = d.get('fpath_local') or ''
            existe = os.path.exists(fpath)
            ext = os.path.splitext(fpath)[1].lower() if fpath else ''
            resultado.append({
                'id': d['id'],
                'num_nf': d['num_nf'],
                'tipo': d['tipo'],
                'emissao': d['emissao'],
                'valor': d['valor'],
                'filename': os.path.basename(fpath) if fpath else '',
                'ext': ext,
                'existe': existe,
                'created_at': d['created_at']
            })

        # 3. Também busca arquivos fisicamente na pasta temp_data por nome de NF
        temp_dir = os.path.join("temp_data", "attachments")
        if os.path.exists(temp_dir):
            for subdir in os.listdir(temp_dir):
                if f"nf_{nf_str}" in subdir or f"_{nf_str}_" in subdir:
                    full_subdir = os.path.join(temp_dir, subdir)
                    if os.path.isdir(full_subdir):
                        for fname in os.listdir(full_subdir):
                            fpath_temp = os.path.join(full_subdir, fname)
                            ext = os.path.splitext(fname)[1].lower()
                            if ext in ('.pdf', '.xml') and not any(r['filename'] == fname for r in resultado):
                                resultado.append({
                                    'id': None,
                                    'num_nf': nf_str,
                                    'tipo': 'PDF' if ext == '.pdf' else 'XML',
                                    'emissao': None,
                                    'valor': None,
                                    'filename': fname,
                                    'ext': ext,
                                    'existe': True,
                                    'fpath_temp': fpath_temp,
                                    'created_at': None
                                })

        return {"documentos": resultado, "total": len(resultado)}
    finally:
        conn.close()


@router.get("/documentos/{doc_id}/visualizar")
def visualizar_documento(doc_id: int, x_company_cnpj: str = Header(...)):
    """Retorna o arquivo como base64 para visualização/download no frontend."""
    cnpj = get_cnpj(x_company_cnpj)
    conn = conectar(cnpj)
    conn.row_factory = dict_factory
    try:
        doc = conn.cursor().execute(
            "SELECT fpath_local, tipo FROM documentos_fiscais WHERE id = ?", (doc_id,)
        ).fetchone()

        if not doc:
            raise HTTPException(status_code=404, detail="Documento não encontrado.")

        fpath = doc.get('fpath_local') or ''
        if not os.path.exists(fpath):
            raise HTTPException(status_code=404, detail="Arquivo não encontrado no disco.")

        with open(fpath, 'rb') as f:
            data = f.read()

        b64 = base64.b64encode(data).decode('utf-8')
        ext = os.path.splitext(fpath)[1].lower()
        mimetype = 'application/pdf' if ext == '.pdf' else 'application/xml'
        filename = os.path.basename(fpath)

        return {"base64": b64, "mimetype": mimetype, "filename": filename}
    finally:
        conn.close()


@router.get("/documentos/arquivo")
def servir_arquivo_temp(fpath: str, x_company_cnpj: str = Header(...)):
    """Serve arquivos de temp_data direto como bytes (para PDF viewer inline)."""
    get_cnpj(x_company_cnpj)  # valida auth
    # Segurança: só permite arquivos dentro das pastas conhecidas do projeto
    base_dirs = [os.path.abspath("temp_data"), os.path.abspath("data")]
    abs_path = os.path.abspath(fpath)
    if not any(abs_path.startswith(b) for b in base_dirs):
        raise HTTPException(status_code=403, detail="Acesso negado.")
    if not os.path.exists(abs_path):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")

    with open(abs_path, 'rb') as f:
        data = f.read()
    ext = os.path.splitext(abs_path)[1].lower()
    mimetype = 'application/pdf' if ext == '.pdf' else 'application/xml'
    return Response(content=data, media_type=mimetype,
                    headers={'Content-Disposition': f'inline; filename="{os.path.basename(abs_path)}"'})


@router.get("/alertas/vencimento-proximo")
def alertas_vencimento_proximo(dias: int = 2, x_company_cnpj: str = Header(...)):
    """Retorna clientes com títulos vencendo em X dias (padrão: 2)."""
    cnpj = get_cnpj(x_company_cnpj)
    conn = conectar(cnpj)
    conn.row_factory = dict_factory
    try:
        alvo = (datetime.datetime.now() + datetime.timedelta(days=dias)).strftime("%d/%m/%Y")
        res = conn.cursor().execute(
            "SELECT pagador, numero_nf, vencimento, valor FROM titulos WHERE vencimento = ? AND status = 'Aberto' AND acao = 'Cobrar'",
            (alvo,)
        ).fetchall()
        return {"alvo": alvo, "titulos": res, "total": len(res)}
    finally:
        conn.close()


# ─── GESTÃO DE CONVERSAS (WhatsApp) ─────────────────────────

@router.get("/conversations")
def list_conversations(x_company_cnpj: str = Header(...)):
    cnpj = get_cnpj(x_company_cnpj)
    conn = conectar(cnpj)
    conn.row_factory = dict_factory
    try:
        res = conn.cursor().execute(
            "SELECT id, numero_whatsapp, cliente_nome, estado, ultima_interacao, ultima_mensagem_enviada, history_json FROM webhook_sessions ORDER BY id DESC"
        ).fetchall()

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
