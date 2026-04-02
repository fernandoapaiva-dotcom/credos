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

        # Log do evento recebido
        with open(log_file, "a") as f:
            f.write(f"[WEBHOOK] Evento: {event} | Instância: {instance_name}\n")

        # Evento de QR Code gerado
        if event == "QRCODE_UPDATED":
            qr_base64 = data.get("qrcode", {}).get("base64") or data.get("base64", "")
            
            if qr_base64:
                # Garantir formato correto
                if not qr_base64.startswith("data:image"):
                    qr_base64 = f"data:image/png;base64,{qr_base64}"
                
                # Salvar QR Code em arquivo específico da instância
                qr_file = os.path.join(data_dir, f"qr_{instance_name}.txt")
                with open(qr_file, "w") as f:
                    f.write(qr_base64)
                
                with open(log_file, "a") as f:
                    f.write(f"[WEBHOOK] QR Code salvo para instância: {instance_name} ({len(qr_base64)} chars)\n")

        # Evento de status de conexão
        elif event == "CONNECTION_UPDATE":
            status = data.get("state", "")
            with open(log_file, "a") as f:
                f.write(f"[WEBHOOK] Status de conexão: {status} para {instance_name}\n")
            
            # Se conectou, apagar QR Code antigo
            if status == "open":
                qr_file = os.path.join(data_dir, f"qr_{instance_name}.txt")
                if os.path.exists(qr_file):
                    os.remove(qr_file)

        return {"status": "ok"}
    
    except Exception as e:
        return {"status": "error", "detail": str(e)}
