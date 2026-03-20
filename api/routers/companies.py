from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import List, Optional
from src.database import carregar_todas_unidades_db, cadastrar_unidade_central, excluir_unidade_central, carregar_configuracoes_db, salvar_configuracoes_db
from src.manager import Manager
from src.evolution_controller import EvolutionController

router = APIRouter()

class CompanyCreate(BaseModel):
    nome: str
    cnpj: str

@router.get("/")
def list_companies():
    unidades = carregar_todas_unidades_db()
    # Adicionar configs como logo_b64 se precisar
    for u in unidades:
        conf = carregar_configuracoes_db(u['empresa_cnpj'])
        u['logo_b64'] = conf.get('logo_b64', '')
    return {"companies": unidades}

@router.post("/")
def add_company(company: CompanyCreate):
    sucesso, msg = cadastrar_unidade_central(company.nome, company.cnpj)
    if sucesso:
        return {"message": msg, "success": True}
    else:
        raise HTTPException(status_code=400, detail=msg)

@router.put("/{cnpj}")
def update_company(cnpj: str, company: CompanyCreate):
    from src.database import atualizar_unidade_central
    sucesso, msg = atualizar_unidade_central(cnpj, company.nome, company.cnpj)
    if sucesso:
        return {"message": msg, "success": True}
    else:
        raise HTTPException(status_code=400, detail=msg)

@router.delete("/{cnpj}")
def delete_company(cnpj: str):
    sucesso, msg = excluir_unidade_central(cnpj)
    if sucesso:
        return {"message": msg, "success": True}
    else:
        raise HTTPException(status_code=400, detail=msg)

@router.get("/{cnpj}/config")
def get_company_config(cnpj: str):
    conf = carregar_configuracoes_db(cnpj)
    if not conf:
        raise HTTPException(status_code=404, detail="Config não encontrada")
    return conf

@router.patch("/{cnpj}/config")
def update_company_config(cnpj: str, updates: dict):
    salvar_configuracoes_db(cnpj, updates)
    return {"success": True, "message": "Configurações atualizadas."}

@router.get("/{cnpj}/scheduler")
def get_scheduler(cnpj: str):
    mgr = Manager(cnpj)
    return {"scheduler": mgr.obter_agendamento()}

@router.post("/{cnpj}/scheduler")
def update_scheduler(cnpj: str, sched: dict):
    # Expects {'dias': [], 'hora': '09:00', 'ignorar_feriados': True, 'ativo': True}
    mgr = Manager(cnpj)
    mgr.salvar_config_agendamento(
        dias=sched.get("dias", []),
        hora=sched.get("hora", "09:00"),
        ignorar_feriados=sched.get("ignorar_feriados", True),
        ativo=sched.get("ativo", False)
    )
    return {"success": True, "message": "Agendamento salvo."}

@router.post("/{cnpj}/whatsapp/status")
def whatsapp_status(cnpj: str):
    conf = carregar_configuracoes_db(cnpj)
    nome_instancia = str(cnpj).replace('.', '').replace('/', '').replace('-', '')
    
    # Needs valid global evo_url and evo_key set in .env or config
    evo = EvolutionController(config=conf, nome_empresa_cliente=nome_instancia)
    status = evo.checar_status()
    return {"status": status}

@router.post("/{cnpj}/whatsapp/create")
def whatsapp_create(cnpj: str):
    conf = carregar_configuracoes_db(cnpj)
    nome_instancia = str(cnpj).replace('.', '').replace('/', '').replace('-', '')
    evo = EvolutionController(config=conf, nome_empresa_cliente=nome_instancia)
    
    res = evo.criar_instancia()
    if "error" in res and "already exists" not in str(res).lower() and "already in use" not in str(res).lower():
        raise HTTPException(status_code=400, detail=str(res.get("error")))
    return {"success": True}

@router.get("/{cnpj}/whatsapp/qr")
def whatsapp_qr(cnpj: str):
    conf = carregar_configuracoes_db(cnpj)
    nome_instancia = str(cnpj).replace('.', '').replace('/', '').replace('-', '')
    evo = EvolutionController(config=conf, nome_empresa_cliente=nome_instancia)
    
    qr = evo.buscar_qrcode()
    if not qr:
        # Might take a few seconds
        raise HTTPException(status_code=404, detail="QR Code não disponivel ainda")
    return {"qr_code_base64": qr}

@router.delete("/{cnpj}/whatsapp")
def whatsapp_delete(cnpj: str):
    conf = carregar_configuracoes_db(cnpj)
    nome_instancia = str(cnpj).replace('.', '').replace('/', '').replace('-', '')
    evo = EvolutionController(config=conf, nome_empresa_cliente=nome_instancia)
    evo.deletar_instancia()
    return {"success": True}

@router.post("/{cnpj}/email/test")
def email_test(cnpj: str):
    conf = carregar_configuracoes_db(cnpj)
    import smtplib
    try:
        smtp_server = conf.get('smtp_server', 'smtp.gmail.com')
        user = conf.get('fin_mail_user', '')
        pwd = conf.get('fin_mail_pass', '')
        if not user or not pwd:
            raise HTTPException(status_code=400, detail="Usuário e senha não configurados.")
        
        server = smtplib.SMTP(smtp_server, 587)
        server.starttls()
        server.login(user, pwd)
        server.quit()
        return {"success": True, "message": "✅ Conexão SMTP (Envio) bem sucedida!"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro de Conexão SMTP: {str(e)}")

@router.post("/{cnpj}/email/test-imap")
def email_test_imap(cnpj: str):
    conf = carregar_configuracoes_db(cnpj)
    import imaplib
    try:
        imap_server = conf.get('imap_server', 'imap.gmail.com')
        user = conf.get('base_mail_user', '')
        pwd = conf.get('base_mail_pass', '')
        if not user or not pwd:
            raise HTTPException(status_code=400, detail="Usuário e senha Base não configurados.")
        
        mail = imaplib.IMAP4_SSL(imap_server)
        mail.login(user, pwd)
        mail.logout()
        return {"success": True, "message": "✅ Conexão IMAP (Recebimento) bem sucedida!"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro de Conexão IMAP: {str(e)}")

@router.post("/{cnpj}/ai/test")
def ai_test(cnpj: str):
    conf = carregar_configuracoes_db(cnpj)
    api_key = conf.get('gemini_api_key', '')
    if not api_key:
        raise HTTPException(status_code=400, detail="Chave API não configurada.")
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents='Responda exatamente com a palavra "Sucesso".'
        )
        return {"success": True, "message": f"Conexão OK! IA respondeu: {response.text}"}
    except Exception as e:
        
        # fallback to 2.0 or 1.5 if 2.5 fails
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents='Responda, de forma curta, "Sucesso".'
            )
            return {"success": True, "message": f"Conexão OK (Fallback)! IA respondeu: {response.text}"}
        except Exception as e2:
            raise HTTPException(status_code=400, detail=f"Erro de Conexão IA: {str(e2)}")

