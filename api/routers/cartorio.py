from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from src.database import conectar
import json
from datetime import datetime

router = APIRouter(tags=["cartorio"])

class CartorioProcessRequest(BaseModel):
    cnpj_empresa: str
    titulo_ids: List[int]

@router.post("/processar-massa")
async def processar_massa(req: CartorioProcessRequest):
    conn = conectar(req.cnpj_empresa)
    c = conn.cursor()
    try:
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for tid in req.titulo_ids:
            # Verifica se já existe um job pendente ou processando
            exist = c.execute("SELECT id FROM cartorio_jobs WHERE titulo_id=? AND status_automacao IN ('Pendente', 'Processando')", (tid,)).fetchone()
            if not exist:
                c.execute("""
                    INSERT INTO cartorio_jobs (titulo_id, status_automacao, data_execucao)
                    VALUES (?, ?, ?)
                """, (tid, 'Pendente', agora))
        conn.commit()
        return {"message": f"{len(req.titulo_ids)} títulos adicionados à fila de processamento do cartório."}
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
