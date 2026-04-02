from fastapi import APIRouter, Request
import os
import json

router = APIRouter()

@router.post("/webhook")
@router.post("/webhook/{sub_path:path}")
async def evolution_webhook(request: Request, sub_path: str = ""):
    """
    Recebe eventos da Evolution API v2 (QRCODE_UPDATED, CONNECTION_UPDATE).
    Salva o QR Code em arquivo para o frontend buscar.
    """
    try:
        body = await request.json()
        
        event = body.get("event", "")
        instance_name = body.get("instance", "")
        data = body.get("data", {})

        # Diretório de dados
        if os.name == 'nt':
            data_dir = r"C:\Antigravity\credos"
        else:
            data_dir = os.path.join(os.getcwd(), "data")
        
        os.makedirs(data_dir, exist_ok=True)
        log_file = os.path.join(data_dir, "EVO_DEBUG.txt")

        # Log do evento recebido com payload completo para debug
        with open(log_file, "a") as f:
            f.write(f"[WEBHOOK] Evento: {event} | Instância: {instance_name} | Payload: {json.dumps(body)[:500]}\n")

        if event == "QRCODE_UPDATED" or "qr" in event.lower() or "base64" in data or "qrcode" in data:
            qr_base64 = data.get("qrcode", {}).get("base64") if isinstance(data.get("qrcode"), dict) else data.get("qrcode")
            if not qr_base64:
                qr_base64 = data.get("base64", "")
            
            if qr_base64 and isinstance(qr_base64, str) and len(qr_base64) > 50:
                # Garantir formato correto
                if not qr_base64.startswith("data:image"):
                    qr_base64 = f"data:image/png;base64,{qr_base64}"
                
                # Salvar QR Code em arquivo específico da instância
                qr_file = os.path.join(data_dir, f"qr_{instance_name}.txt")
                with open(qr_file, "w") as f:
                    f.write(qr_base64)
                
                with open(log_file, "a") as f:
                    f.write(f"[WEBHOOK] QR Code salvo para instância: {instance_name} ({len(qr_base64)} chars)\n")

        # Evento de status de conexão independente do QR
        if event == "CONNECTION_UPDATE" or "connection" in event.lower():
            status = data.get("state", "") or data.get("status", "")
            with open(log_file, "a") as f:
                f.write(f"[WEBHOOK] Status de conexão: {status} para {instance_name}\n")
            
            # Se conectou de fato, apagar QR Code antigo
            if status == "open":
                qr_file = os.path.join(data_dir, f"qr_{instance_name}.txt")
                if os.path.exists(qr_file):
                    os.remove(qr_file)

        return {"status": "ok"}
    
    except Exception as e:
        return {"status": "error", "detail": str(e)}
