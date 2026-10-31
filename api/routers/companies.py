from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import List, Optional
from src.database import carregar_todas_unidades_db, cadastrar_unidade_central, excluir_unidade_central, carregar_configuracoes_db, salvar_configuracoes_db, is_global_halt_active, set_global_halt
from src.manager import Manager
from src.evolution_controller import EvolutionController

router = APIRouter()

class CompanyCreate(BaseModel):
    nome: str
    cnpj: str

@router.get("/")
def list_companies():
    unidades = carregar_todas_unidades_db()
    # Removemos o carregamento de logos em massa para acelerar a listagem
    # e evitar que o JSON fique gigantesco, travando o frontend.
    return {"companies": unidades}

@router.post("/")
def add_company(company: CompanyCreate):
    sucesso, msg = cadastrar_unidade_central(company.nome, company.cnpj)
    if sucesso:
        return {"message": msg, "success": True}
    else:
        raise HTTPException(status_code=400, detail=msg)

@router.put("/{cnpj:path}")
def update_company(cnpj: str, company: CompanyCreate):
    from src.database import atualizar_unidade_central
    sucesso, msg = atualizar_unidade_central(cnpj, company.nome, company.cnpj)
    if sucesso:
        return {"message": msg, "success": True}
    else:
        raise HTTPException(status_code=400, detail=msg)

@router.delete("/{cnpj:path}")
def delete_company(cnpj: str):
    sucesso, msg = excluir_unidade_central(cnpj)
    if sucesso:
        return {"message": msg, "success": True}
    else:
        raise HTTPException(status_code=400, detail=msg)

@router.get("/{cnpj:path}/config")
def get_company_config(cnpj: str):
    conf = carregar_configuracoes_db(cnpj)
    if not conf:
        raise HTTPException(status_code=404, detail="Config não encontrada")
    return conf

from fastapi import BackgroundTasks

@router.patch("/{cnpj:path}/config")
def update_company_config(cnpj: str, updates: dict, background_tasks: BackgroundTasks):
    salvar_configuracoes_db(cnpj, updates)
    
    # Se o operador do whatsapp foi alterado, aciona a sincronização de grupo em background
    if 'operador_whatsapp' in updates:
        from src.group_sync import sincronizar_grupo_operadores
        background_tasks.add_task(sincronizar_grupo_operadores, cnpj)
        
    return {"success": True, "message": "Configurações atualizadas."}

@router.get("/{cnpj:path}/scheduler")
def get_scheduler(cnpj: str):
    mgr = Manager(cnpj)
    return {"scheduler": mgr.obter_agendamento()}

@router.post("/{cnpj:path}/scheduler")
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

@router.post("/{p1}/whatsapp/status")
@router.post("/{p1}/{p2}/whatsapp/status")
def whatsapp_status(p1: str, p2: str = None):
    cnpj = f"{p1}/{p2}" if p2 else p1
    conf = carregar_configuracoes_db(cnpj)
    nome_instancia = str(cnpj).replace('.', '').replace('/', '').replace('-', '')
    
    evo = EvolutionController(config=conf, nome_empresa_cliente=nome_instancia)
    status = evo.checar_status()
    if status in ["close", "closed", "disconnected"]:
        status = "closed"
    elif status in ["open", "connected"]:
        status = "open"
    return {"status": status}

@router.post("/{p1}/whatsapp/create")
@router.post("/{p1}/{p2}/whatsapp/create")
def whatsapp_create(p1: str, p2: str = None):
    cnpj = f"{p1}/{p2}" if p2 else p1
    conf = carregar_configuracoes_db(cnpj)
    nome_instancia = str(cnpj).replace('.', '').replace('/', '').replace('-', '')
    evo = EvolutionController(config=conf, nome_empresa_cliente=nome_instancia)
    
    res = evo.criar_instancia()
    if "error" in res and "already exists" not in str(res).lower() and "already in use" not in str(res).lower():
        raise HTTPException(status_code=400, detail=str(res.get("error")))
    
    qr = evo.buscar_qrcode()
    return {"success": True, "qr_code_base64": qr}

@router.get("/{p1}/whatsapp/qr")
@router.get("/{p1}/{p2}/whatsapp/qr")
def whatsapp_qr(p1: str, p2: str = None):
    cnpj = f"{p1}/{p2}" if p2 else p1
    conf = carregar_configuracoes_db(cnpj)
    nome_instancia = str(cnpj).replace('.', '').replace('/', '').replace('-', '')
    evo = EvolutionController(config=conf, nome_empresa_cliente=nome_instancia)
    
    qr = evo.buscar_qrcode()
    if not qr:
        # Might take a few seconds
        raise HTTPException(status_code=404, detail="QR Code não disponivel ainda")
    return {"qr_code_base64": qr}

@router.delete("/{cnpj:path}/whatsapp")
def whatsapp_delete(cnpj: str):
    conf = carregar_configuracoes_db(cnpj)
    nome_instancia = str(cnpj).replace('.', '').replace('/', '').replace('-', '')
    evo = EvolutionController(config=conf, nome_empresa_cliente=nome_instancia)
    evo.deletar_instancia()
    return {"success": True}

@router.post("/{cnpj:path}/email/test")
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

@router.post("/{cnpj:path}/email/test-imap")
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

@router.post("/{cnpj}/whatsapp/send")
def whatsapp_send(cnpj: str, payload: dict):
    """Envia uma mensagem de texto simples via WhatsApp."""
    conf = carregar_configuracoes_db(cnpj)
    nome_instancia = str(cnpj).replace('.', '').replace('/', '').replace('-', '')
    evo = EvolutionController(config=conf, nome_empresa_cliente=nome_instancia)
    
    number = payload.get("number")
    message = payload.get("message")
    
    if not number or not message:
        raise HTTPException(status_code=400, detail="Número e mensagem são obrigatórios.")
    
    sucesso = evo.enviar_mensagem_texto(number, message)
    if not sucesso:
        raise HTTPException(status_code=500, detail="Falha ao enviar mensagem via Evolution API.")
    
    return {"success": True}

@router.post("/{cnpj}/ai/test")
def ai_test(cnpj: str):
    conf = carregar_configuracoes_db(cnpj)
    api_key = conf.get('gemini_api_key', '')
    if not api_key:
        raise HTTPException(status_code=400, detail="Chave API não configurada.")
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        # Ajustado para 2.0-flash pois 2.5 não existe e 1.5 está instável/descont.
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents='Responda em português: "IA Conectada com Sucesso".'
        )
        return {"success": True, "message": f"Conexão OK! IA respondeu: {response.text}"}
    except Exception as e:
        import re
        err_msg = str(e)
        err_msg = re.sub(r'AIzaSy[a-zA-Z0-9_\-]{33}', '[CHAVE_REDIGIDA]', err_msg)
        err_msg = re.sub(r'AQ\.[a-zA-Z0-9_\-]{30,}', '[CHAVE_REDIGIDA]', err_msg)
        raise HTTPException(status_code=400, detail=f"Erro de Conexão IA: {err_msg}")

from fastapi import BackgroundTasks

@router.post("/{cnpj}/ai/trigger")
def ai_trigger(cnpj: str, background_tasks: BackgroundTasks):
    from src.worker import disparar_negociacoes_ia
    background_tasks.add_task(disparar_negociacoes_ia, cnpj, True)
    return {"success": True, "message": "Disparo IA iniciado em segundo plano com sucesso."}

@router.post("/{cnpj:path}/cartorio/test-cert")
def test_cartorio_cert(cnpj: str):
    conf = carregar_configuracoes_db(cnpj)
    pfx_b64 = conf.get('cartorio_pfx_b64')
    password = conf.get('cartorio_pfx_pass')
    
    if not pfx_b64 or not password:
        raise HTTPException(status_code=400, detail="Certificado e Senha precisam ser inseridos e salvos primeiro.")
    
    import base64
    try:
        from cryptography.hazmat.primitives.serialization import pkcs12
        from cryptography.x509.oid import NameOID
        
        # Verifica se tem prefixo data:application e remove
        if ',' in pfx_b64:
            pfx_b64 = pfx_b64.split(',')[1]
            
        pfx_data = base64.b64decode(pfx_b64)
        private_key, certificate, additional_certificates = pkcs12.load_key_and_certificates(pfx_data, password.encode())
        
        subj = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        cn = subj[0].value if subj else "Desconhecido"
        
        return {"success": True, "message": f"✅ Certificado Válido! ({cn})"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"❌ Erro ao ler certificado. Verifique a senha e o arquivo (.pfx ou .p12). Erro: {str(e)}")

@router.post("/{cnpj:path}/whatsapp/group/create")
def whatsapp_group_create(cnpj: str):
    """
    Cria automaticamente o grupo de relatórios para a empresa.
    Adiciona os diretores configurados no campo 'diretores_whatsapp'.
    """
    conf = carregar_configuracoes_db(cnpj)
    diretores_raw = conf.get('diretores_whatsapp', '')
    nome_empresa = conf.get('empresa_nome', 'Empresa')
    
    if not diretores_raw:
        raise HTTPException(status_code=400, detail="Nenhum número de diretor configurado.")
    
    # Limpa e valida os números
    diretores = [n.strip() for n in diretores_raw.replace(',', ';').split(';') if n.strip()]
    
    nome_instancia = str(cnpj).replace('.', '').replace('/', '').replace('-', '')
    evo = EvolutionController(config=conf, nome_empresa_cliente=nome_instancia)
    
    # Verifica conexão
    status = evo.checar_status()
    if status != "open":
        raise HTTPException(status_code=400, detail="WhatsApp não está conectado. Conecte primeiro para criar o grupo.")
    
    # Criar grupo
    subject = f"Relatórios Analu - {nome_empresa}"
    description = f"Grupo de relatórios diários e notificações financeiras da Analu para {nome_empresa}."
    
    res = evo.criar_grupo(subject=subject, participants=diretores, description=description)
    
    if res and (res.get("id") or (isinstance(res, dict) and "gid" in str(res))):
        group_jid = res.get("id") or res.get("gid")
        # Se veio como objeto complexo no v1.8.2 da Evolution
        if not group_jid and "group" in res:
            group_jid = res["group"].get("id")

        if group_jid:
            salvar_configuracoes_db(cnpj, {"grupo_relatorio_jid": group_jid})
            return {"success": True, "message": f"✅ Grupo '{subject}' criado com sucesso!", "jid": group_jid}
    
    err_detail = str(res.get("error")) if res else "Erro desconhecido na Evolution API"
    raise HTTPException(status_code=500, detail=f"Falha ao criar grupo: {err_detail}")

@router.get("/system/halt")
def get_system_halt():
    return {"halt": is_global_halt_active()}

@router.post("/system/halt")
def post_system_halt(payload: dict):
    halt = payload.get("halt", False)
    set_global_halt(halt)
    return {"success": True, "halt": halt}
