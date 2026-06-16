from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File
from pydantic import BaseModel
from typing import List
from src.database import conectar, carregar_configuracoes_db
import json
from datetime import datetime
import os
import shutil
import uuid

router = APIRouter(tags=["cartorio"])

class CartorioProcessRequest(BaseModel):
    cnpj_empresa: str
    titulo_ids: List[int]

@router.post("/processar-massa")
async def processar_massa(req: CartorioProcessRequest, background_tasks: BackgroundTasks):
    conn = conectar(req.cnpj_empresa)
    c = conn.cursor()
    try:
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for tid in req.titulo_ids:
            # Verifica se já existe um job pendente ou processando
            exist = c.execute("SELECT id FROM cartorio_jobs WHERE titulo_id=? AND status_automacao IN ('Pendente', 'Processando')", (tid,)).fetchone()
            if not exist:
                c.execute("""
                    INSERT INTO cartorio_jobs (titulo_id, status_automacao, data_execucao, intervacao_manual)
                    VALUES (?, ?, ?, 1)
                """, (tid, 'Pendente', agora))
        conn.commit()
        
        # Dispara processamento da fila imediatamente no background
        from src.worker import processar_fila_cartorio
        background_tasks.add_task(processar_fila_cartorio, req.cnpj_empresa)
        
        return {"message": f"{len(req.titulo_ids)} títulos adicionados à fila e processamento iniciado."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.get("/status/{cnpj_empresa}")
async def get_cartorio_status(cnpj_empresa: str):
    conn = conectar(cnpj_empresa)
    conn.row_factory = json_row_factory
    try:
        # Busca últimos jobs e detalhes dos títulos
        query = """
            SELECT cj.*, t.numero_nf, t.pagador, t.valor
            FROM cartorio_jobs cj
            JOIN titulos t ON t.id = cj.titulo_id
            ORDER BY cj.id DESC LIMIT 50
        """
        res = conn.cursor().execute(query).fetchall()
        return [dict(r) for r in res]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

def json_row_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

@router.post("/status/{cnpj_empresa}/{job_id}/upload-nf")
async def upload_nf_cartorio(cnpj_empresa: str, job_id: int, file: UploadFile = File(...)):
    conn = conectar(cnpj_empresa)
    conn.row_factory = __import__('sqlite3').Row
    c = conn.cursor()
    
    try:
        job = c.execute("SELECT titulo_id FROM cartorio_jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            raise HTTPException(status_code=404, detail="Job do cartório não encontrado.")
            
        titulo_id = job['titulo_id']
        
        # Salva o arquivo temporariamente
        temp_dir = os.path.join("temp_data", "attachments")
        os.makedirs(temp_dir, exist_ok=True)
        ext = os.path.splitext(file.filename)[1]
        temp_path = os.path.join(temp_dir, f"nf_manual_{uuid.uuid4().hex}{ext}")
        
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # Extrai a data de emissão
        config = carregar_configuracoes_db(cnpj_empresa)
        from src.mail_scanner import MailScanner
        scanner = MailScanner(config)
        
        dados = scanner.extrair_dados_fiscais(temp_path)
        
        if not dados or not dados.get('emissao'):
            raise HTTPException(status_code=400, detail="Não foi possível extrair a Data de Emissão (dhEmi ou similar) deste arquivo. Verifique se é uma NF válida.")
            
        # Atualiza o banco
        c.execute("UPDATE titulos SET emissao=? WHERE id=?", (dados['emissao'], titulo_id))
        c.execute("UPDATE cartorio_jobs SET status_automacao='Pendente', log_erro='' WHERE id=?", (job_id,))
        conn.commit()
        
        return {"message": "Data de emissão extraída com sucesso. O título retornou para a fila de processamento."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.post("/status/{cnpj_empresa}/{job_id}/reset")
async def reset_job_cartorio(cnpj_empresa: str, job_id: int):
    conn = conectar(cnpj_empresa)
    c = conn.cursor()
    try:
        c.execute("UPDATE cartorio_jobs SET status_automacao='Pendente', log_erro='' WHERE id=?", (job_id,))
        if c.rowcount == 0:
            raise HTTPException(status_code=404, detail="Job não encontrado.")
        conn.commit()
        return {"message": "Título retornado para a fila com sucesso."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.get("/next-job/{cnpj_empresa}")
async def get_next_job(cnpj_empresa: str):
    """Retorna o próximo job pendente para o robô local."""
    conn = conectar(cnpj_empresa)
    conn.row_factory = __import__('sqlite3').Row
    c = conn.cursor()
    try:
        # Busca o primeiro job Pendente cujo título já tenha data de emissão
        query = """
            SELECT cj.id as job_id, t.id as titulo_id, t.numero_nf, t.pagador, t.valor, t.emissao, t.vencimento, 
                   cli.whatsapp, cli.nome as cliente_nome, cli.cnpj, cli.email, cli.endereco
            FROM cartorio_jobs cj
            JOIN titulos t ON t.id = cj.titulo_id
            JOIN clientes cli ON cli.nome = t.pagador
            WHERE cj.status_automacao = 'Pendente' AND t.emissao IS NOT NULL
            ORDER BY cj.id ASC LIMIT 1
        """
        job = c.execute(query).fetchone()
        
        pdf_base64 = None
        if job and job.get('numero_nf'):
            import os, base64
            nf_str = str(job['numero_nf']).lstrip('0')
            doc = c.execute("SELECT fpath_local FROM documentos_fiscais WHERE (num_nf = ? OR num_nf LIKE ?) AND fpath_local LIKE '%.pdf' ORDER BY created_at DESC LIMIT 1", (nf_str, f"%{nf_str}%")).fetchone()
            if doc and doc.get('fpath_local') and os.path.exists(doc['fpath_local']):
                try:
                    with open(doc['fpath_local'], 'rb') as f:
                        pdf_base64 = base64.b64encode(f.read()).decode('utf-8')
                except Exception as e:
                    print(f"Erro ao ler PDF para cartorio: {e}")
        
        if job:
            job_dict = dict(job)
            job_dict['pdf_base64'] = pdf_base64
            
            c.execute("UPDATE cartorio_jobs SET status_automacao = 'Processando', log_erro = '', data_execucao = ? WHERE id = ?", (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), job['job_id']))
            conn.commit()
            return {"job": job_dict}
        
        return {"job": None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

class JobStatusRequest(BaseModel):
    status: str # "Sucesso" ou "Erro"
    log_erro: str = ""

@router.post("/job/{cnpj_empresa}/{job_id}/status")
async def update_job_status(cnpj_empresa: str, job_id: int, req: JobStatusRequest):
    """Recebe o resultado do robô local."""
    conn = conectar(cnpj_empresa)
    conn.row_factory = __import__('sqlite3').Row
    c = conn.cursor()
    try:
        job = c.execute("SELECT titulo_id FROM cartorio_jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            raise HTTPException(status_code=404, detail="Job não encontrado")
            
        titulo_id = job['titulo_id']
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        c.execute("""
            UPDATE cartorio_jobs 
            SET status_automacao=?, log_erro=?, data_execucao=?
            WHERE id=?
        """, (req.status, req.log_erro, agora, job_id))
        
        if req.status == "Sucesso":
            c.execute("UPDATE titulos SET status='Cartório', data_envio_cartorio=?, status_retorno_cartorio='Aguardando' WHERE id=?", (agora, titulo_id))
            
            # Notifica o cliente
            try:
                t = c.execute("SELECT numero_nf, valor, pagador FROM titulos WHERE id=?", (titulo_id,)).fetchone()
                cli = c.execute("SELECT nome, whatsapp FROM clientes WHERE nome=?", (t['pagador'],)).fetchone()
                
                config = carregar_configuracoes_db(cnpj_empresa)
                from src.evolution_controller import EvolutionController
                evo = EvolutionController(config=config, nome_empresa_cliente=cnpj_empresa)
                
                whatsapp = str(cli.get('whatsapp', ''))
                if whatsapp:
                    numeros = [n.strip() for n in whatsapp.split(';') if n.strip()]
                    msg_cartorio = (
                        f"*Analu (Assistente Virtual) Diz:*\n\n"
                        f"Olá, {str(cli['nome']).split()[0]}. Conforme avisado anteriormente, "
                        f"como não chegamos a um acordo efetivo após nossas tentativas de negociação, "
                        f"informamos que o título *NF {t['numero_nf']}* no valor de *R$ {float(t['valor']):,.2f}* "
                        f"foi encaminhado para *protesto em cartório*.\n\n"
                        f"Para regularização, será necessário efetuar o pagamento do débito, aguardar a emissão "
                        f"da carta de anuência por nossa parte e, posteriormente, apresentar esta carta "
                        f"junto ao cartório competente, efetuando o pagamento das custas e emolumentos cartoriais.\n\n"
                        f"Caso tenha dúvidas sobre o procedimento, entre em contato com nosso departamento financeiro."
                    )
                    for num in numeros:
                        evo.enviar_mensagem_texto(num, msg_cartorio)
            except Exception as e:
                print(f"Erro ao enviar notificação de cartório: {e}")
                
        conn.commit()
        return {"message": "Status atualizado com sucesso"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

class TituloUpdate(BaseModel):
    emissao: str
    vencimento: str
    numero_nf: str
    valor: float

@router.put("/titulo/{titulo_id}")
def update_titulo_cartorio(titulo_id: int, payload: TituloUpdate, x_company_cnpj: str = Header(...)):
    """Edita os dados do título e reseta o job associado para Pendente"""
    cnpj = get_cnpj(x_company_cnpj)
    conn = conectar(cnpj)
    try:
        c = conn.cursor()
        c.execute("""
            UPDATE titulos
            SET emissao = ?, vencimento = ?, numero_nf = ?, valor = ?
            WHERE id = ?
        """, (payload.emissao, payload.vencimento, payload.numero_nf, payload.valor, titulo_id))
        
        c.execute("""
            UPDATE cartorio_jobs
            SET status_automacao = 'Pendente', log_erro = ''
            WHERE titulo_id = ?
        """, (titulo_id,))
        
        conn.commit()
        return {"success": True}
    finally:
        conn.close()
