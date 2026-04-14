from fastapi import APIRouter, HTTPException
from src.proactive_scanner import ProactiveScanner
from src.database import conectar
import threading

router = APIRouter(tags=["proactive"])
scanner = ProactiveScanner()

@router.get("/status/{cnpj}")
async def get_proactive_status(cnpj: str):
    """Retorna o total de documentos indexados no repositório local."""
    try:
        conn = conectar(cnpj)
        cursor = conn.cursor()
        count = cursor.execute("SELECT count(*) FROM documentos_fiscais").fetchone()[0]
        conn.close()
        return {"total_documentos": count}
    except Exception as e:
        return {"total_documentos": 0, "error": str(e)}

@router.post("/index-history/{cnpj}")
async def index_history(cnpj: str):
    """Dispara a indexação retroativa em background."""
    try:
        # Iniciamos em uma thread separada para não travar a API
        thread = threading.Thread(target=scanner.indexar_retroativo, args=(cnpj, 180))
        thread.start()
        return {"success": True, "message": "Indexação histórica iniciada em segundo plano."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
