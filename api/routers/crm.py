from fastapi import APIRouter, HTTPException, Header, Response, UploadFile, File, Form
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
    data_promessa: Optional[str] = None # Data prometida pelo cliente (YYYY-MM-DD ou DD/MM/YYYY)

class ChargePayload(BaseModel):
    canais: List[str] = ["whatsapp", "email"]

@router.get("/clients")
def get_clients(x_company_cnpj: str = Header(...)):
    cnpj = get_cnpj(x_company_cnpj)
    clientes = listar_clientes_db(cnpj)
    
    conn = conectar(cnpj)
    conn.row_factory = dict_factory
    c = conn.cursor()
    try:
        import json as _json
        
        SUCESSO_STATUS = ('Sucesso', 'Sucesso Parcial', 'Sucesso Total')
        COBRANCA_TIPOS = ('Cobrança Manual', 'WhatsApp/Email', 'Cobrança Automática', 'Cobrança Individual')
        
        for cli in clientes:
            nome = cli.get('nome', '').strip()
            
            # 1. Check if client has unresolved titles
            try:
                row_unresolved = c.execute("""
                    SELECT count(*) as cnt FROM titulos
                    WHERE trim(pagador) = ? AND status NOT IN ('Pago', 'Baixado', 'Cancelado')
                """, (nome,)).fetchone()
                has_unresolved = (row_unresolved.get('cnt', 0) > 0) if row_unresolved else False
            except:
                has_unresolved = False
            
            # 2. Count charges per channel by parsing detalhes JSON
            total_whatsapp = 0
            total_email = 0
            total_analu = 0
            
            # Fetch all charge logs for this client
            try:
                logs = c.execute("""
                    SELECT tipo_envio, status, detalhes FROM logs_envio
                    WHERE cliente = ?
                    AND tipo_envio IN ('Cobrança Manual', 'WhatsApp/Email', 'Cobrança Automática', 'Cobrança Individual')
                """, (nome,)).fetchall()
                
                for log in logs:
                    status = log.get('status', '')
                    detalhes_raw = log.get('detalhes', '') or ''
                    
                    # Try to parse detalhes as JSON
                    try:
                        det = _json.loads(detalhes_raw)
                    except:
                        det = {}
                    
                    # Count WhatsApp: res_wa is True, or canais.whatsapp contains "OK"
                    wa_ok = False
                    email_ok = False
                    
                    if isinstance(det, dict):
                        # Format 1: {"res_wa": true/false, "res_email": true/false}
                        if 'res_wa' in det:
                            wa_ok = bool(det.get('res_wa'))
                        if 'res_email' in det:
                            email_ok = bool(det.get('res_email'))
                        
                        # Format 2: {"canais": {"whatsapp": "OK (1/1)", "email": "..."}}
                        canais = det.get('canais', {})
                        if isinstance(canais, dict):
                            wa_val = str(canais.get('whatsapp', '') or '')
                            mail_val = str(canais.get('email', '') or '')
                            if 'OK' in wa_val or 'Enviado' in wa_val:
                                wa_ok = True
                            if 'OK' in mail_val or 'Enviado' in mail_val:
                                email_ok = True
                    
                    # If no JSON info but status is success, count as WhatsApp (legacy)
                    if not det and status in SUCESSO_STATUS:
                        wa_ok = True
                    
                    if wa_ok:
                        total_whatsapp += 1
                    if email_ok:
                        total_email += 1
                        
            except Exception as e:
                print(f"Erro ao contar cobranças de {nome}: {e}")
            
            # 3. Count Analu (negociacoes)
            try:
                row_neg = c.execute("""
                    SELECT count(*) as cnt FROM negociacoes
                    WHERE cliente = ?
                """, (nome,)).fetchone()
                total_analu = (row_neg.get('cnt', 0)) if row_neg else 0
            except:
                total_analu = 0
            
            total_cobrancas = total_whatsapp + total_email + total_analu
            
            cli['has_unresolved'] = has_unresolved
            cli['total_cobrancas'] = total_cobrancas
            cli['cobrancas_whatsapp'] = total_whatsapp
            cli['cobrancas_email'] = total_email
            cli['cobrancas_analu'] = total_analu
            
    except Exception as e:
        print(f"Erro ao enriquecer dados dos clientes no CRM: {e}")
    finally:
        conn.close()
        
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
            SET nome=?, cnpj=?, whatsapp=?, email=?, contato=?, scanner_pendente=0
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
    
    # Enriquece cada título com o contador de cobranças enviadas por canal (logs_envio + negociacoes)
    conn = conectar(cnpj)
    conn.row_factory = dict_factory
    c = conn.cursor()
    try:
        import json as _json
        SUCESSO_STATUS = ('Sucesso', 'Sucesso Parcial', 'Sucesso Total')
        
        # Obter todos os logs_envio do cliente para evitar consultas repetidas
        logs = c.execute("""
            SELECT tipo_envio, status, detalhes FROM logs_envio
            WHERE cliente = ?
            AND tipo_envio IN ('Cobrança Manual', 'WhatsApp/Email', 'Cobrança Automática', 'Cobrança Individual')
        """, (nome,)).fetchall()
        
        # Obter todas as negociacoes do cliente
        negociacoes = c.execute("""
            SELECT titulos_ids FROM negociacoes
            WHERE cliente = ?
        """, (nome,)).fetchall()
        
        for t in titulos:
            nf = str(t.get('numero_nf', '') or '').strip()
            total_whatsapp = 0
            total_email = 0
            total_analu = 0
            
            # 1. Conta nos logs de envio (WhatsApp/Email manual e automático)
            for log in logs:
                status = log.get('status', '')
                detalhes_raw = log.get('detalhes', '') or ''
                
                try:
                    det = _json.loads(detalhes_raw)
                except:
                    det = {}
                
                if not isinstance(det, dict):
                    continue
                
                # Check if this log references the specific NF
                contains_nf = False
                
                # Format A: {"titulos": ["15093"]} or similar list of strings/ints
                titulos_list = det.get('titulos', [])
                if isinstance(titulos_list, list):
                    for item in titulos_list:
                        if isinstance(item, dict):
                            # Format B: {"titulos": [{"numero_nf": "19078", "valor": 1200.0}]}
                            if str(item.get('numero_nf', '')).strip() == nf:
                                contains_nf = True
                                break
                        elif str(item).strip() == nf:
                            contains_nf = True
                            break
                            
                if not contains_nf:
                    continue
                    
                # Determine channels if NF is present
                wa_ok = False
                email_ok = False
                
                # Format 1: {"res_wa": true, "res_email": true}
                if 'res_wa' in det:
                    wa_ok = bool(det.get('res_wa'))
                if 'res_email' in det:
                    email_ok = bool(det.get('res_email'))
                
                # Format 2: {"canais": {"whatsapp": "OK (1/1)", "email": "..."}}
                canais = det.get('canais', {})
                if isinstance(canais, dict):
                    wa_val = str(canais.get('whatsapp', '') or '')
                    mail_val = str(canais.get('email', '') or '')
                    if 'OK' in wa_val or 'Enviado' in wa_val:
                        wa_ok = True
                    if 'OK' in mail_val or 'Enviado' in mail_val:
                        email_ok = True
                
                # If no specific channel info but status is successful, count as WhatsApp (legacy)
                if 'res_wa' not in det and 'canais' not in det and status in SUCESSO_STATUS:
                    wa_ok = True
                
                if wa_ok:
                    total_whatsapp += 1
                if email_ok:
                    total_email += 1
            
            # 2. Conta nas negociações IA (Analu)
            for neg in negociacoes:
                titulos_ids_raw = neg.get('titulos_ids', '') or ''
                # titulos_ids can be a JSON array or a comma-separated string, or simple string
                try:
                    t_ids = _json.loads(titulos_ids_raw)
                except:
                    t_ids = [x.strip() for x in titulos_ids_raw.split(',') if x.strip()]
                
                contains_nf_analu = False
                if isinstance(t_ids, list):
                    if any(str(x).strip() == nf for x in t_ids):
                        contains_nf_analu = True
                elif str(t_ids).strip() == nf:
                    contains_nf_analu = True
                
                if contains_nf_analu:
                    total_analu += 1
            
            t['total_cobranças'] = total_whatsapp + total_email + total_analu
            t['cobrancas_whatsapp'] = total_whatsapp
            t['cobrancas_email'] = total_email
            t['cobrancas_analu'] = total_analu
            
    except Exception as e:
        print(f"Aviso: não foi possível calcular total_cobranças por título: {e}")
    finally:
        conn.close()
    
    return {"titles": titulos}

@router.patch("/titles/{id_titulo}")
def update_title_status(id_titulo: int, update: TitleStatusUpdate, x_company_cnpj: str = Header(...)):
    cnpj = get_cnpj(x_company_cnpj)
    
    novo_status = update.status
    nova_acao = update.acao
    
    # Se o status é pago, automaticamente podemos baixar.
    if novo_status == "Pago":
        novo_status = "Baixado"
        nova_acao = "Pausar"
    elif novo_status in ["Baixado", "Cancelado"]:
        nova_acao = "Pausar"
        
    atualizar_titulo_status_acao(cnpj, id_titulo, novo_status, nova_acao)
    
    # Salva data_promessa se fornecida (Item 7)
    if update.data_promessa is not None:
        conn = conectar(cnpj)
        try:
            val = update.data_promessa.strip() if update.data_promessa.strip() else None
            conn.cursor().execute(
                "UPDATE titulos SET data_promessa = ? WHERE id = ?",
                (val, id_titulo)
            )
            conn.commit()
        except Exception as e:
            print(f"Aviso: falha ao salvar data_promessa: {e}")
        finally:
            conn.close()
    
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


# ─── UPLOAD MANUAL DE DOCUMENTOS POR TÍTULO (Item 9) ─────────────────────

@router.post("/titles/{id_titulo}/documentos/upload")
async def upload_documento_titulo(
    id_titulo: int,
    tipo: str = Form(...),  # NFe, NFS, Fatura, Boleto, XML
    arquivo: UploadFile = File(...),
    x_company_cnpj: str = Header(...)
):
    """
    Permite adicionar manualmente NFe, NFS, Fatura de Locação, Boleto ou XML a um título.
    O arquivo é salvo em temp_data/manual_docs/ e indexado na tabela documentos_fiscais.
    """
    cnpj = get_cnpj(x_company_cnpj)
    
    TIPOS_VALIDOS = ['NFe', 'NFS', 'Fatura', 'Boleto', 'XML']
    if tipo not in TIPOS_VALIDOS:
        raise HTTPException(status_code=400, detail=f"Tipo inválido. Use: {', '.join(TIPOS_VALIDOS)}")
    
    conn = conectar(cnpj)
    conn.row_factory = dict_factory
    try:
        titulo = conn.cursor().execute(
            "SELECT * FROM titulos WHERE id = ?", (id_titulo,)
        ).fetchone()
        if not titulo:
            raise HTTPException(status_code=404, detail="Título não encontrado.")
        
        # Salva o arquivo no disco
        ext = os.path.splitext(arquivo.filename)[1].lower() if arquivo.filename else '.pdf'
        save_dir = os.path.join("temp_data", "manual_docs", str(id_titulo))
        os.makedirs(save_dir, exist_ok=True)
        
        filename_safe = f"{tipo}_{titulo['numero_nf']}_{titulo['pagador'][:20].replace(' ','_')}{ext}"
        save_path = os.path.join(save_dir, filename_safe)
        
        content = await arquivo.read()
        with open(save_path, 'wb') as f:
            f.write(content)
        
        # Indexa na tabela documentos_fiscais
        agora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.cursor().execute("""
            INSERT INTO documentos_fiscais 
            (cnpj_cliente, num_nf, tipo, fpath_local, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, ('manual', titulo['numero_nf'], tipo, save_path, agora))
        conn.commit()
        
        return {"success": True, "message": f"Documento '{tipo}' salvo e indexado com sucesso.", "filename": filename_safe}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao salvar documento: {str(e)}")
    finally:
        conn.close()


@router.get("/alertas/sem-documentos")
def alertas_sem_documentos(x_company_cnpj: str = Header(...)):
    """
    Retorna títulos abertos que não possuem documentos indexados.
    Usado pela Analu para avisar o grupo Admin que precisam de arquivos. (Item 11)
    """
    cnpj = get_cnpj(x_company_cnpj)
    conn = conectar(cnpj)
    conn.row_factory = dict_factory
    try:
        # Títulos abertos
        titulos = conn.cursor().execute(
            "SELECT t.id, t.pagador, t.numero_nf, t.vencimento, t.valor, c.cnpj "
            "FROM titulos t LEFT JOIN clientes c ON trim(c.nome) = trim(t.pagador) "
            "WHERE t.status = 'Aberto' AND t.acao = 'Cobrar'"
        ).fetchall()
        
        sem_docs = []
        for t in titulos:
            nf = str(t.get('numero_nf', '') or '').lstrip('0').strip()
            doc = conn.cursor().execute(
                "SELECT id FROM documentos_fiscais WHERE num_nf = ? OR num_nf LIKE ? LIMIT 1",
                (nf, f"%{nf}%")
            ).fetchone()
            if not doc:
                # Verifica também no temp_data fisicamente
                temp_dir = os.path.join("temp_data", "attachments")
                encontrou_fisico = False
                if os.path.exists(temp_dir):
                    for sub in os.listdir(temp_dir):
                        if nf in sub:
                            encontrou_fisico = True
                            break
                if not encontrou_fisico:
                    sem_docs.append(t)
        
        return {"sem_documentos": sem_docs, "total": len(sem_docs)}
    finally:
        conn.close()
