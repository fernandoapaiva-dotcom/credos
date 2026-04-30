from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from pydantic import BaseModel
from src.manager import Manager
from src.rag_negotiator import RAGNegotiator
from src.database import conectar
import json

router = APIRouter(tags=["negotiation"])

class NegotiateRequest(BaseModel):
    cnpj_empresa: str
    cliente_nome: str

class NegotiationLog(BaseModel):
    id: int
    cliente: str
    mensagem: str
    data: str
    status: str

@router.post("/generate")
async def generate_negotiation(req: NegotiateRequest):
    try:
        mgr = Manager(req.cnpj_empresa)
        rag = RAGNegotiator(req.cnpj_empresa)
        
        # Agrupa débitos do cliente
        debitos = mgr.agrupar_debitos_por_cliente()
        if req.cliente_nome not in debitos:
            raise HTTPException(status_code=404, detail="Cliente não possui débitos pendentes para negociação.")
        
        info = debitos[req.cliente_nome]
        
        # Gera proposta via IA (RAG)
        proposta, erro = rag.gerar_proposta_ia(req.cliente_nome, info)
        
        if erro:
            raise HTTPException(status_code=500, detail=f"Erro na IA: {erro}")
        
        return {
            "cliente": req.cliente_nome,
            "proposta": proposta,
            "total": info['total'],
            "qtd_titulos": len(info['itens'])
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class SendNegotiationRequest(BaseModel):
    cnpj_empresa: str
    cliente_nome: str
    whatsapp_numbers: List[str]
    mensagem: str

@router.post("/send")
async def send_negotiation(req: SendNegotiationRequest):
    try:
        from src.database import conectar, carregar_configuracoes_db
        from src.evolution_controller import EvolutionController
        from datetime import datetime
        import json

        config = carregar_configuracoes_db(req.cnpj_empresa)
        evo = EvolutionController(config, req.cnpj_empresa)
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = conectar(req.cnpj_empresa)
        c = conn.cursor()
        
        history = [{"role": "model", "text": req.mensagem}]
        history_str = json.dumps(history)

        for num in req.whatsapp_numbers:
            num_clean = "".join(filter(str.isdigit, str(num)))
            # Cria sessão ativa
            c.execute(
                "INSERT INTO webhook_sessions (numero_whatsapp, cliente_nome, dia_cobranca, estado, history_json, ultima_mensagem_enviada, ultima_interacao) VALUES (?,?,1,'aguardando_resposta',?,?,?)",
                (num_clean, req.cliente_nome, history_str, req.mensagem, agora)
            )
            # Aciona bot Evolution
            evo.enviar_mensagem_texto(num_clean, req.mensagem)
            
        conn.commit()
        conn.close()

        return {"success": True, "message": "Enviado e sessão ativada com sucesso!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history/{cnpj_empresa}")
async def get_negotiation_history(cnpj_empresa: str):
    conn = conectar(cnpj_empresa)
    conn.row_factory = json_row_factory
    try:
        c = conn.cursor()
        res = c.execute("SELECT * FROM negociacoes ORDER BY id DESC LIMIT 50").fetchall()
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
