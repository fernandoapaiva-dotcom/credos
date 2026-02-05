import streamlit as st
import os
import time
import base64
import pandas as pd
from dotenv import load_dotenv
from streamlit_option_menu import option_menu

load_dotenv()

from src.database import (
    salvar_configuracoes_db, carregar_configuracoes_db, inicializar_banco, 
    salvar_dados_no_banco, carregar_todas_unidades_db, 
    verificar_login, alterar_senha_usuario, listar_clientes_db, excluir_cliente_db,
    salvar_log_envio, listar_titulos_por_cliente, criar_usuario, listar_usuarios, excluir_usuario
)
from src.manager import Manager
from src.mail_scanner import conectar_email, MailScanner
from src.evolution_controller import EvolutionController
from src.extractor import ler_pdf_bruto, processar_dataframe_mapeado

st.set_page_config(page_title="Credos SaaS", page_icon="🛡️", layout="wide", initial_sidebar_state="collapsed")
inicializar_banco()

# --- CSS ---
st.markdown("""
<style>
    #MainMenu {visibility: hidden;} .stDeployButton {display: none;} footer {visibility: hidden;} header {visibility: hidden;}
    .block-container {padding-top: 0.5rem; padding-bottom: 2rem;}
    .gmail-avatar-text { width: 40px; height: 40px; border-radius: 50%; background-color: #8e24aa; color: white; text-align: center; line-height: 40px; font-weight: bold; cursor: pointer; }
    .gmail-avatar-img { width: 40px; height: 40px; border-radius: 50%; object-fit: cover; border: 1px solid #ddd; cursor: pointer; }
    .header-right { display: flex; justify-content: flex-end; align-items: center; gap: 10px; font-family: sans-serif; }
    .company-name { font-weight: 500; font-size: 14px; color: #333; }
</style>
""", unsafe_allow_html=True)

def renderizar_avatar_gmail(nome, logo_b64):
    if logo_b64: return f'<img src="data:image/png;base64,{logo_b64}" class="gmail-avatar-img" title="{nome}">'
    iniciais = "".join([n[0] for n in nome.split()[:2]]).upper() if nome else "US"
    return f'<div class="gmail-avatar-text" title="{nome}">{iniciais}</div>'

def renderizar_logo(b64_string, tamanho=50):
    if b64_string: return f'<img src="data:image/png;base64,{b64_string}" style="width:{tamanho}px; height:{tamanho}px; border-radius:50%; vertical-align:middle; border:2px solid #eee;">'
    return "🏢"

if 'logged_in' not in st.session_state: st.session_state.logged_in = False

def fazer_login():
    if verificar_login(st.session_state.u_input, st.session_state.p_input):
        st.session_state.logged_in = True
        st.session_state.usuario_atual = st.session_state.u_input
        st.rerun()
    else: st.error("Dados incorretos.")

def fazer_logout():
    st.session_state.logged_in = False
    st.session_state.config = {}
    if 'usuario_atual' in st.session_state: del st.session_state.usuario_atual
    st.rerun()

# --- TELA DE LOGIN ---
if not st.session_state.logged_in:
    c1, c2, c3 = st.columns([1,1,1])
    with c2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.title("🛡️ Credos System")
        with st.form("login_form"):
            st.text_input("Usuário", key="u_input")
            st.text_input("Senha", type="password", key="p_input")
            st.form_submit_button("Entrar", on_click=fazer_login, use_container_width=True)
    st.stop()

# --- CARREGAMENTO ---
if 'config' not in st.session_state: st.session_state.config = carregar_configuracoes_db() or {}
conf = st.session_state.config

# Injeção Automática do .ENV
if os.getenv("EVO_API_URL"): st.session_state.config['evo_url'] = os.getenv("EVO_API_URL")
if os.getenv("EVO_GLOBAL_KEY"): st.session_state.config['evo_key'] = os.getenv("EVO_GLOBAL_KEY")
if os.getenv("GEMINI_API_KEY"): st.session_state.config['gemini_key'] = os.getenv("GEMINI_API_KEY")

mgr = Manager(conf['empresa_cnpj']) if conf.get('empresa_cnpj') else None

if not conf.get('empresa_cnpj') and 'novo_cadastro' not in st.session_state:
    st.session_state.novo_cadastro = True

# --- HEADER ---
col_logo, col_menu = st.columns([6, 2])
with col_logo:
    if conf.get('empresa_nome'):
        logo_html = renderizar_logo(conf.get('logo_b64'), 35)
        st.markdown(f"### {logo_html} {conf.get('empresa_nome')}", unsafe_allow_html=True)
    else: st.markdown("### 🛡️ Credos Painel")

with col_menu:
    nome_empresa = conf.get('empresa_nome', 'Admin')
    avatar_html = renderizar_avatar_gmail(nome_empresa, conf.get('logo_b64'))
    st.markdown(f"""<div class="header-right"><span class="company-name">{nome_empresa}</span>{avatar_html}</div>""", unsafe_allow_html=True)
    with st.popover("🔻 Opções", use_container_width=True):
        st.caption(f"Logado: {st.session_state.get('usuario_atual')}")
        if st.button("🔄 Trocar Empresa", use_container_width=True):
            st.session_state.ir_para_gestao = True
            st.rerun()
        if st.button("🚪 Sair", type="primary", use_container_width=True): fazer_logout()

st.divider()

idx_padrao = 1 if st.session_state.get('ir_para_gestao') else 0
if st.session_state.get('ir_para_gestao'): st.session_state.ir_para_gestao = False

selected = option_menu(
    menu_title=None, options=["Operacional", "Gestão", "Configurações"],
    icons=["hdd-stack", "building-gear", "sliders"], default_index=idx_padrao, orientation="horizontal",
    styles={"container": {"padding": "0!important", "background-color": "#f8f9fa"}}
)

# ==============================================================================
# OPERACIONAL
# ==============================================================================
if selected == "Operacional":
    if not mgr:
        st.warning("⚠️ Nenhuma empresa selecionada.")
        st.stop()
    
    t1, t2, t3, t4 = st.tabs(["📂 Importar PDF", "💸 Cobrança (Envio)", "👥 CRM & Carteira", "📊 Relatórios"])

    with t1:
        st.info("⚠️ Importação de Boletos PDF.")
        c_up, c_conf = st.columns([1, 2])
        up_pdf = c_up.file_uploader("Upload Boletos (PDF)", type="pdf")
        
        if up_pdf:
            with st.spinner("Lendo..."): df_bruto = ler_pdf_bruto(up_pdf)
            if df_bruto is not None:
                with c_conf:
                    st.markdown("##### Pré-visualização:")
                    st.dataframe(df_bruto.head(5), width="stretch")
                    st.write("**Mapeamento:**")
                    cols = df_bruto.columns.tolist()
                    c1, c2, c3, c4 = st.columns(4)
                    col_venc = c1.selectbox("Vencimento", cols, index=0)
                    col_num = c2.selectbox("Número/NF", cols, index=min(1, len(cols)-1))
                    col_val = c3.selectbox("Valor", cols, index=min(2, len(cols)-1))
                    col_pag = c4.selectbox("Cliente", cols, index=min(3, len(cols)-1))
                    
                    if st.button("💾 Salvar no CRM", type="primary"):
                        mapa = {'vencimento': col_venc, 'numero': col_num, 'valor': col_val, 'pagador': col_pag}
                        dados = processar_dataframe_mapeado(df_bruto, mapa)
                        novos = 0
                        for t in dados:
                            salvar_dados_no_banco([t], conf['empresa_cnpj'])
                            # Cadastra cliente automaticamente se não existir
                            if not mgr.verificar_cliente_existe(t['pagador']):
                                mgr.cadastrar_cliente_completo(t['pagador'], "", "", "", "Financeiro")
                                novos += 1
                        st.toast(f"✅ {len(dados)} títulos salvos!", icon="💾")
                        if novos: st.success(f"{novos} clientes novos cadastrados no CRM!")
                        time.sleep(2)
                        st.rerun()

    with t2:
        st.caption("Apenas títulos com ação 'Cobrar' aparecem aqui.")
        rel = mgr.agrupar_debitos_por_cliente()
        if not rel: 
            st.success("Nenhuma pendência para cobrar hoje.")
        else:
            for cli, info in rel.items():
                qtd = len(info['itens'])
                with st.expander(f"🔴 {cli} | Total: R$ {info['total']:,.2f}"):
                    # --- CORREÇÃO AQUI: info['itens'] em vez de info['detalhes'] ---
                    st.dataframe(pd.DataFrame(info['itens']), width="stretch")
                    
                    c1, c2 = st.columns([1, 1])
                    key_zip = f"zip_{cli}"
                    
                    with c1:
                        st.write("📄 **1. Preparar Arquivos**")
                        # Botão gera o ZIP sempre que clicado, garantindo atualização
                        if st.button(f"🔍 Zipar {qtd} Boletos", key=f"bz_{cli}"):
                            with st.spinner(f"Buscando PDFs para {cli}..."):
                                path, n = mgr.buscar_e_zipar_pdfs(cli, info['itens'])
                                if path:
                                    st.session_state[key_zip] = path
                                    st.toast(f"📦 {n} boletos encontrados e zipados!", icon="✅")
                                else: 
                                    st.error("Nenhum PDF encontrado (Verifique e-mail no CRM).")
                        
                        if st.session_state.get(key_zip):
                            st.success("✅ Arquivo pronto.")
                            with open(st.session_state[key_zip], "rb") as f:
                                st.download_button("⬇️ Baixar ZIP", f, file_name=f"boletos_{cli}.zip", key=f"dl_{cli}")
                    
                    with c2:
                        st.write("🚀 **2. Disparar Cobrança**")
                        
                        # --- GERAÇÃO AUTOMÁTICA DA MENSAGEM ---
                        dados_do_cliente = info['dados_cliente'] 
                        # --- CORREÇÃO AQUI: info['itens'] ---
                        msg_auto = mgr.gerar_mensagem_cobranca(cli, dados_do_cliente, info['total'], info['itens'])
                        
                        msg = st.text_area("Texto (Editável)", msg_auto, key=f"tx_{cli}", height=250)
                        zip_pronto = st.session_state.get(key_zip)
                        
                        if st.button("📧 Enviar Email & WhatsApp", key=f"s_{cli}", type="primary", disabled=(not zip_pronto)):
                            with st.status("Iniciando envio...", expanded=True) as status:
                                status.write("📤 Enviando e-mail...")
                                resultado_cobranca = mgr.executar_processo_completo_cobranca(cli, msg, zip_pronto)
                                
                                if resultado_cobranca.get('email'): 
                                    status.write("✅ E-mail enviado com sucesso!")
                                else: 
                                    status.error("❌ Falha no E-mail. Verifique o servidor SMTP.")
                                    
                                status.write("📱 Enviando WhatsApp...")
                                if resultado_cobranca.get('whatsapp'): 
                                    status.write("✅ WhatsApp enviado com sucesso!")
                                else: 
                                    status.error("❌ Falha no WhatsApp.")
                                    st.warning("Verifique o terminal para ver o erro técnico da Evolution API.")
                                
                                status.update(label="Processo de Cobrança Finalizado!", state="complete", expanded=False)
                                salvar_log_envio(cli, 'Auto', "Disparo Múltiplo", 'Concluído')

    with t3:
        st.subheader("👥 Gestão de Clientes e Carteira")
        all_clis = listar_clientes_db()
        nomes = [c['nome'] for c in all_clis]
        
        with st.expander("➕ Adicionar Novo Cliente Manualmente"):
            with st.form("new_cli_man"):
                cn1, cn2, cn3, cn4, cn5 = st.columns(5)
                nm_new = cn1.text_input("Nome/Razão Social")
                cp_new = cn2.text_input("CNPJ")
                wa_new = cn3.text_input("WhatsApp")
                em_new = cn4.text_input("E-mail")
                ct_new = cn5.text_input("Contato (Pessoa)", placeholder="Ex: João")
                
                if st.form_submit_button("Cadastrar"):
                    if nm_new:
                        mgr.cadastrar_cliente_completo(nm_new, cp_new, wa_new, em_new, ct_new)
                        st.success(f"Cliente {nm_new} cadastrado!")
                        time.sleep(1)
                        st.rerun()
                    else: st.error("Nome é obrigatório.")

        st.divider()
        cli_sel = st.selectbox("Selecione um Cliente:", ["-- Selecione --"] + nomes)
        
        if cli_sel != "-- Selecione --":
            dados = next(c for c in all_clis if c['nome'] == cli_sel)
            with st.container(border=True):
                st.write(f"**Dados de: {cli_sel}**")
                with st.form("edit_cli"):
                    c1, c2, c3, c4 = st.columns(4)
                    nc = c1.text_input("CNPJ", value=dados['cnpj'] or "")
                    nm = c2.text_input("E-mail", value=dados['email'] or "")
                    nz = c3.text_input("WhatsApp", value=dados['whatsapp'] or "")
                    nt = c4.text_input("Contato Ref.", value=dados['contato'] or "")
                    
                    if st.form_submit_button("💾 Atualizar Cadastro"):
                        mgr.cadastrar_cliente_completo(cli_sel, nc, nz, nm, nt)
                        st.toast("Atualizado!", icon="✅")
                        time.sleep(1)
                        st.rerun()
                
                if st.button("🗑️ Excluir Cliente e Títulos", type="secondary"):
                    excluir_cliente_db(dados['id'], cli_sel)
                    st.success("Removido com sucesso.")
                    time.sleep(1)
                    st.rerun()

            st.markdown("### 💳 Títulos do Cliente")
            titulos = listar_titulos_por_cliente(cli_sel)
            if titulos:
                df_t = pd.DataFrame(titulos)
                df_t.insert(0, "Selecionar", False)
                df_edit = st.data_editor(
                    df_t[['Selecionar', 'id', 'numero_nf', 'vencimento', 'valor', 'status', 'acao']],
                    column_config={
                        "Selecionar": st.column_config.CheckboxColumn("✅", width="small"),
                        "id": st.column_config.NumberColumn("ID", disabled=True, width="small"),
                        "numero_nf": st.column_config.TextColumn("NF", disabled=True),
                        "valor": st.column_config.NumberColumn("Valor", disabled=True, format="R$ %.2f"),
                        "acao": st.column_config.SelectboxColumn("Ação Individual", width="medium", options=["Cobrar", "Não Cobrar", "Cartório", "Em Negociação", "Acordo Feito"]),
                        "status": st.column_config.TextColumn("Status", disabled=True)
                    },
                    hide_index=True, width="stretch", key=f"editor_{cli_sel}"
                )
                if st.button("💾 Salvar Alterações Individuais", key="save_ind"):
                    df_to_save = df_edit.drop(columns=['Selecionar'])
                    df_to_save['data_promessa'] = None 
                    if mgr.salvar_edicao_titulos(df_to_save):
                        st.toast("Salvo!", icon="✅")
                        time.sleep(1)
                        st.rerun()

                st.divider()
                st.write("⚡ **Ações em Massa:**")
                col_m1, col_m2 = st.columns([2, 1])
                acao_massa = col_m1.selectbox("Escolha a Ação:", ["Cobrar", "Não Cobrar", "Cartório", "Em Negociação", "Acordo Feito"], key="sel_massa")
                
                if col_m2.button("Aplicar a Selecionados"):
                    selecionados = df_edit[df_edit['Selecionar'] == True]
                    if not selecionados.empty:
                        ids_para_atualizar = selecionados['id'].tolist()
                        if mgr.aplicar_acao_em_lote(ids_para_atualizar, acao_massa):
                            st.success(f"Ação '{acao_massa}' aplicada a {len(ids_para_atualizar)} títulos!")
                            time.sleep(1.5)
                            st.rerun()
                    else: st.warning("Nenhum título selecionado.")
            else: st.info("Nenhum título cadastrado.")

    with t4: st.info("Relatórios em breve.")

# ==============================================================================
# GESTÃO
# ==============================================================================
elif selected == "Gestão":
    st.subheader("🏢 Unidades")
    unidades = carregar_todas_unidades_db()
    cols = st.columns(3)
    for u in unidades:
        with cols[0]:
            with st.container(border=True):
                st.markdown(f"**{u['empresa_nome']}**")
                if str(u.get('id')) == str(conf.get('id')): 
                    c_ativa1, c_ativa2 = st.columns(2)
                    c_ativa1.button("✅ Ativa", key=f"k_{u['id']}", disabled=True)
                    if c_ativa2.button("✏️ Editar", key=f"edit_{u['id']}"):
                         st.session_state.novo_cadastro = True
                         st.rerun()
                else: 
                    if st.button("Acessar", key=f"go_{u['id']}"):
                        st.session_state.config = u
                        st.rerun()
    if st.button("➕ Nova Filial"):
        st.session_state.novo_cadastro = True
        st.session_state.config = {}
        st.rerun()

# ==============================================================================
# CONFIGURAÇÕES
# ==============================================================================
elif selected == "Configurações":
    ct1, ct2, ct3, ct4 = st.tabs(["🔐 Minha Senha", "👥 Usuários", "🟢 WhatsApp / IA", "🕵️ E-mail"])
    
    with ct1:
        st.write(f"Alterar senha de: **{st.session_state.usuario_atual}**")
        with st.form("p"):
            s = st.text_input("Nova Senha", type="password")
            if st.form_submit_button("Alterar"):
                alterar_senha_usuario(st.session_state.usuario_atual, s)
                st.success("Senha alterada! Use na próxima vez.")

    with ct2:
        st.subheader("Cadastrar Novos Usuários")
        with st.form("new_user"):
            c1, c2 = st.columns(2)
            u_new = c1.text_input("Login")
            p_new = c2.text_input("Senha", type="password")
            if st.form_submit_button("Criar Usuário"):
                if u_new and p_new:
                    ok, msg = criar_usuario(u_new, p_new)
                    if ok: st.success(msg)
                    else: st.error(msg)
                    time.sleep(1)
                    st.rerun()
                else: st.error("Preencha login e senha.")
        st.divider()
        st.write("📋 **Usuários Existentes:**")
        users = listar_usuarios()
        for u in users:
            c1, c2 = st.columns([4, 1])
            c1.text(f"👤 {u['username']}")
            if c2.button("🗑️", key=f"del_u_{u['id']}"):
                ok, msg = excluir_usuario(u['id'])
                if ok: st.rerun()
                else: st.error(msg)

    with ct3:
        st.markdown("### 🟢 Configuração WhatsApp & IA")
        
        default_url = os.getenv("EVO_API_URL") or conf.get('evo_url') or ""
        default_key = os.getenv("EVO_GLOBAL_KEY") or conf.get('evo_key') or ""
        default_gem = os.getenv("GEMINI_API_KEY") or conf.get('gemini_key') or ""

        with st.expander("🛠️ Editar Configurações de API", expanded=True):
            with st.form("fix_apis"):
                new_url = st.text_input("URL da API (Evolution)", value=default_url)
                new_key = st.text_input("Global Key (Evolution)", value=default_key, type="password")
                new_gem = st.text_input("Gemini API Key", value=default_gem, type="password")
                
                if st.form_submit_button("💾 Salvar TUDO"):
                    st.session_state.config.update({
                        "evo_url": new_url, 
                        "evo_key": new_key,
                        "gemini_key": new_gem
                    })
                    salvar_configuracoes_db(st.session_state.config)
                    st.success("Configurações salvas!")
                    time.sleep(1)
                    st.rerun()

        evo = EvolutionController(st.session_state.config)
        status = evo.checar_status()

        # --- DIAGNÓSTICO VISUAL COM BOTÃO RESET ---
        st.write("---")
        if status and 'status' in status and status['status'] == 401:
             st.error("🚨 **Erro 401: Chave Incorreta**")
             st.info("Verifique se a 'Global Key' nas configurações é a mesma do servidor.")
        
        elif status and 'instance' in status:
            estado = status.get('instance', {}).get('state', 'unknown')
            st.write(f"Status da Instância no Servidor: **{estado}**")
            
            if estado == "open":
                st.success("✅ WhatsApp Conectado!")
                st.caption("Se quiser conectar outro número, use o botão de Resetar abaixo.")
            
            elif estado in ["close", "connecting"]:
                st.warning("⚠️ Instância existe mas está desconectada.")
                if st.button("🔄 Gerar QR Code Agora", key="btn_qr_manual"):
                    qr_data = evo.buscar_qrcode()
                    if qr_data and 'base64' in qr_data:
                        st.image(qr_data['base64'], width=300, caption="Escaneie rápido!")
                    else:
                        st.error("Não foi possível buscar o QR Code. Tente Resetar.")
            
            # BOTÃO DE PÂNICO PARA LIMPAR O SERVIDOR
            st.divider()
            if st.button("🗑️ Resetar Instância (Forçar Novo QR Code)", type="primary", key="btn_reset_inst"):
                with st.spinner("Apagando instância velha no servidor..."):
                    if evo.deletar_instancia():
                        st.success("Instância apagada! Criando uma nova em 3s...")
                        time.sleep(2)
                        st.rerun()
                    else:
                        st.error("Erro ao deletar. Verifique a URL e a Chave.")

        else:
            st.warning(f"Instância '{evo.instance}' não encontrada no servidor.")
            if st.button("🛠️ Criar Instância Agora", key="btn_create_main"):
                with st.spinner("Criando..."):
                    res = evo.criar_instancia()
                    if res and 'qrcode' in res:
                        st.success("Criado com sucesso!")
                        st.image(res['qrcode']['base64'], width=300)
                    elif res and 'instance' in res:
                        st.success("Criado! Clique em Gerar QR Code se ele não aparecer.")
                        st.rerun()
                    else:
                        st.error(f"Erro ao criar: {res}")

    with ct4:
        st.markdown("### 🧪 Laboratório de E-mail")
        scanner = MailScanner(conf)
        if st.button("📂 Listar Pastas"):
            st.code("\n".join(scanner.listar_pastas_debug()))
        st.divider()
        c1, c2 = st.columns(2)
        pasta = c1.text_input("Pasta", value="[Gmail]/E-mails enviados")
        termo = c2.text_input("Termo", value="912")
        # Chave única para evitar erro de duplicidade
        if st.button("Testar Busca", key="btn_test_busca_main"):
            st.text_area("Log", scanner.testar_busca_manual(pasta, termo), height=200)

# ==============================================================================
# WIZARD ATUALIZADO
# ==============================================================================
if st.session_state.get('novo_cadastro', False):
    st.markdown("---")
    st.markdown("## 🧙‍♂️ Assistente de Configuração")
    tabs_wiz = st.tabs(["Identificação", "E-mails", "APIs (Zap/IA)"])
    
    with tabs_wiz[0]:
        n = st.text_input("Nome Fantasia", value=conf.get('empresa_nome', ''))
        c = st.text_input("CNPJ", value=conf.get('empresa_cnpj', ''))
        l = st.file_uploader("Logo", type=["png","jpg"])
        if st.button("Salvar Identificação", key="btn_wiz_ident"):
            logo_str = ""
            if l: logo_str = base64.b64encode(l.getvalue()).decode()
            elif conf.get('logo_b64'): logo_str = conf.get('logo_b64')
            st.session_state.config.update({"empresa_nome": n, "empresa_cnpj": c, "logo_b64": logo_str})
            salvar_configuracoes_db(st.session_state.config)
            st.toast("Salvo!")

    with tabs_wiz[1]:
        c1_mail, c2_mail = st.columns(2)
        with c1_mail:
            st.markdown("### Busca (IMAP)")
            c_g, c_o = st.columns(2)
            if c_g.button("Gmail Bus", key="btn_wiz_gmail_bus"): st.session_state.config.update({"imap_server":"imap.gmail.com"})
            if c_o.button("Outlook Bus", key="btn_wiz_outlook_bus"): st.session_state.config.update({"imap_server":"outlook.office365.com"})
            base_u = st.text_input("User Busca", value=conf.get('mail_base_user', ''))
            base_p = st.text_input("Pass Busca", type="password", value=conf.get('mail_base_pass', ''))
            if st.button("Testar Busca", key="btn_wiz_test_busca"):
                conn, msg = conectar_email(base_u, base_p, conf.get('imap_server',''))
                if conn:
                    st.session_state.config.update({"mail_base_user": base_u, "mail_base_pass": base_p})
                    salvar_configuracoes_db(st.session_state.config)
                    st.success("OK!")
                else: st.error(msg)

        with c2_mail:
            st.markdown("### Envio (SMTP)")
            c_g2, c_o2 = st.columns(2)
            if c_g2.button("Gmail Env", key="btn_wiz_gmail_env"): st.session_state.config.update({"smtp_server":"smtp.gmail.com"})
            if c_o2.button("Outlook Env", key="btn_wiz_outlook_env"): st.session_state.config.update({"smtp_server":"smtp.office365.com"})
            send_u = st.text_input("User Envio", value=conf.get('mail_user', ''))
            send_p = st.text_input("Pass Envio", type="password", value=conf.get('mail_pass', ''))
            display_name = st.text_input("Remetente", value=conf.get('email_envio_display', 'Financeiro'))
            if st.button("Salvar Envio", key="btn_wiz_save_env"):
                st.session_state.config.update({"mail_user": send_u, "mail_pass": send_p, "email_envio_display": display_name})
                salvar_configuracoes_db(st.session_state.config)
                st.success("Salvo!")

    with tabs_wiz[2]:
        c_k1, c_k2, c_k3 = st.columns(3)
        evo_url = c_k1.text_input("URL Evolution", value=conf.get('evo_url', ''))
        evo_key = c_k2.text_input("Key Evolution", value=conf.get('evo_key', ''), type="password")
        gem_key = c_k3.text_input("Gemini Key", value=conf.get('gemini_key', ''), type="password")

        if st.button("Salvar APIs", key="btn_wiz_save_api"):
             st.session_state.config.update({"evo_url": evo_url, "evo_key": evo_key, "gemini_key": gem_key})
             salvar_configuracoes_db(st.session_state.config)
             st.success("Salvo!")
             st.rerun()

        evo_wiz = EvolutionController(st.session_state.config)
        st_wiz = evo_wiz.checar_status()
        
        if st_wiz and 'instance' in st_wiz:
            state_w = st_wiz.get('instance', {}).get('state', 'unknown')
            if state_w == 'open': st.success("✅ Conectado!")
            else:
                if st.button("QR Code", key="btn_wiz_qr"):
                    qr = evo_wiz.buscar_qrcode()
                    if qr and 'base64' in qr: st.image(qr['base64'], width=250)
        else:
            if st.button("Criar Instância", key="btn_wiz_create"):
                res_c = evo_wiz.criar_instancia()
                if res_c and 'qrcode' in res_c: st.image(res_c['qrcode']['base64'], width=250)
        
        st.divider()
        if st.button("🏁 Finalizar", key="btn_wiz_finish"):
            st.session_state.novo_cadastro = False
            st.rerun()

    if st.button("Cancelar", key="btn_wiz_cancel"):
        st.session_state.novo_cadastro = False
        st.rerun()