from fastapi import APIRouter, HTTPException, Header, BackgroundTasks, Response, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from src.manager import Manager
import os
import tempfile
import json

router = APIRouter()

class ReportRequest(BaseModel):
    cliente: str = "Todos"
    data_inicio: str # YYYY-MM-DD
    data_fim: str # YYYY-MM-DD
    tipo: str = "Todos"

def remove_file(path: str):
    if os.path.exists(path):
        try:
            os.remove(path)
        except:
            pass

@router.post("/generate")
def generate_report(req: ReportRequest, x_company_cnpj: str = Header(...)):
    mgr = Manager(x_company_cnpj)
    filtros = {
        "cliente": req.cliente if req.cliente != "Todos" else None,
        "data_inicio": req.data_inicio,
        "data_fim": req.data_fim,
        "tipo": req.tipo
    }
    
    # Log de início para depuração
    print(f"📄 [REPORT] Gerando PDF em memória: {req.tipo} (Empresa: {x_company_cnpj})")
    
    try:
        content = mgr.gerar_relatorio_pdf_cobrancas(filtros)
    except Exception as e:
        print(f"❌ [REPORT] Erro na geração: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno ao gerar PDF: {str(e)}")

    if not content:
        raise HTTPException(status_code=404, detail="Nenhum dado encontrado para o relatório.")

    # Nome amigável do arquivo
    tipo_clean = req.tipo.lower().replace(' ', '_')
    filename = f"relatorio_{tipo_clean}_{req.data_inicio.replace('-', '')}.pdf"
    content_length = len(content)
    
    headers = {
        'Content-Disposition': f'attachment; filename="{filename}"',
        'Content-Length': str(content_length),
        'Access-Control-Expose-Headers': 'Content-Disposition'
    }
    
    return Response(
        content=content, 
        media_type="application/pdf", 
        headers=headers
    )

@router.post("/confront-pdf")
async def confront_pdf(
    x_company_cnpj: str = Header(...),
    layout: Optional[str] = Form(None), # Optional JSON string of layout map
    file: UploadFile = File(...)
):
    try:
        # Save uploaded file to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name

        mapa_layout = None
        if layout:
            try:
                mapa_layout = json.loads(layout)
            except:
                pass

        mgr = Manager(x_company_cnpj)
        result = mgr.confrontar_pdf_banco(tmp_path, mapa_layout)
        
        # Cleanup temp file
        if os.path.exists(tmp_path):
            try: os.remove(tmp_path)
            except: pass
            
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class ExportConfrontRequest(BaseModel):
    columns: List[str]
    rows: List[Dict[str, Any]]

@router.post("/export-confront-pdf")
def export_confront_pdf(req: ExportConfrontRequest, x_company_cnpj: str = Header(...)):
    try:
        mgr = Manager(x_company_cnpj)
        content = mgr.gerar_pdf_confronto(req.dict())
        
        filename = "relatorio_confronto_boletos.pdf"
        content_length = len(content)
        
        headers = {
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Content-Length': str(content_length),
            'Access-Control-Expose-Headers': 'Content-Disposition'
        }
        
        return Response(
            content=content,
            media_type="application/pdf",
            headers=headers
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
