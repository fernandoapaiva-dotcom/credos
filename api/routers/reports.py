from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from src.manager import Manager
import os

router = APIRouter()

class ReportRequest(BaseModel):
    cliente: str = "Todos"
    data_inicio: str # YYYY-MM-DD
    data_fim: str # YYYY-MM-DD
    tipo: str = "Todos"

@router.post("/generate")
def generate_report(req: ReportRequest, x_company_cnpj: str = Header(...)):
    mgr = Manager(x_company_cnpj)
    filtros = {
        "cliente": req.cliente if req.cliente != "Todos" else None,
        "data_inicio": req.data_inicio,
        "data_fim": req.data_fim,
        "tipo": req.tipo
    }
    path = mgr.gerar_relatorio_pdf_cobrancas(filtros)
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Nenhum dado encontrado para gerar o relatório.")
    
    return FileResponse(path, media_type="application/pdf", filename=os.path.basename(path))
