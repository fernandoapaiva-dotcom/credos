import streamlit as st
import os
import time
import base64
import pandas as pd
import datetime
from dotenv import load_dotenv
from streamlit_option_menu import option_menu

# Importações
from src.database import (
    salvar_configuracoes_db, carregar_configuracoes_db, inicializar_banco, 
    salvar_dados_no_banco, carregar_todas_unidades_db, excluir_unidade_db,
    verificar_login, alterar_senha_admin, listar_clientes_db, excluir_cliente_db,
    listar_logs_cliente, listar_chat_cliente, salvar_log_envio, salvar_chat_whatsapp
)
from src.manager import Manager
from src.mail_scanner import conectar_email, MailScanner
from src.evolution_controller import EvolutionController
from src.extractor import ler_pdf_bruto, processar_dataframe_mapeado # NOVO
from src.ai_handler import get_ai_response

load_dotenv()
st.set_page_config(page_title="Credos SaaS", page_icon="🛡️", layout="wide", initial_sidebar_state="collapsed")
inicializar_banco()

# --- CSS E UTILITÁRIOS ---
st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .block-container {padding-top: 1rem; padding-bottom: 1rem;}
    /* Estilo para chat */
    .chat-row { padding: 10px; border-radius: 5px; margin-bottom: 5px; }
    .chat-bot { background-color: #e6f7ff; text-align: right; }
    .chat-cliente { background-color: #f0f0f0; text-align: left; }
</style>
""", unsafe_allow_html=True)

def salvar_logo(file):
    if file: return base64.b64encode(file.getvalue()).decode()
    return st.session_state.config.get('logo_b64')

def renderizar_logo(b64_string, tamanho=50):
    if b64_string:
        return f'<img src="data:image/png;base64,{b64_string}" style="width:{tamanho}px; height:{tamanho}px; border-radius:50%; vertical-align:middle; border:2px solid #ddd;">'
    return "🏢"

# --- LOGIN ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
def fazer_login():
    if verificar_login(st.session_state.u_input, st.session_state.p_input):
        st.session_state.logged_in = True
    else: st.error("Dados incorretos.")

if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1,1,1])
    with col2:
        st.title("🛡️ Credos System")
        with st.form("login"):
            st.text_input("Usuário", key="u_input")
            st.text_input("Senha", type="password", key="p_input")
            st.form_submit_button("Entrar", on_click=fazer_login)
    st.stop()

# --- APP PRINCIPAL ---
if 'config' not in st.session_state: st.session_state.config = carregar_configuracoes_db() or {}
conf = st.session_state.config
mgr = Manager(conf['empresa_cnpj']) if conf.get('empresa_cnpj') else None

if not conf.get('empresa_cnpj') and 'novo_cadastro' not in st.session_state:
    st.session_state.novo_cadastro = True

# MENU SUPERIOR
selected = option_menu(
    menu_title=None,
    options=["Operacional", "Gestão", "Configurações", "Sair"],
    icons=["hdd-stack", "building-gear", "sliders", "box-arrow-right"],
    menu_icon="cast", default_index=0, orientation="horizontal",
    styles={"container": {"padding": "0!important", "background-color": "#f0f2f6"}}
)

# ==============================================================================
# 1. OPERACIONAL
# ==============================================================================
if selected == "Operacional":
    if not mgr:
        st.warning("⚠️ Selecione uma empresa na aba Gestão.")
        st.stop()

    # --- CABEÇALHO COM LOGO CORRETA ---
    logo_html = renderizar_logo(conf.get('logo_b64'), 60)
    st.markdown(f"### {logo_html} {conf.get('empresa_nome')} | Painel Operacional", unsafe_allow_html=True)
    
    t1, t2, t3, t4 = st.tabs(["📂 Carga de Dados", "💸 Executar Cobrança", "👥 Clientes (CRM)", "📊 Relatórios"])

    # --- ABA 1: CARGA DE DADOS (DINÂMICA) ---
    with t1:
        st.info("Importe PDFs de qualquer banco e mapeie as colunas.")
        
        c_up, c_conf = st.columns([1, 2])
        
        with c_up:
            up_pdf = st.file_uploader("Upload PDF", type="pdf")
        
        if up_pdf:
            # 1. Lê o PDF Bruto
            with st.spinner("Lendo PDF..."):
                df_bruto = ler_pdf_bruto(up_pdf)
            
            if df_bruto is not None:
                with c_conf:
                    st.write("🔍 **Mapeamento de Colunas:**")
                    st.caption("Indique qual coluna do PDF corresponde aos dados do sistema.")
                    
                    cols_encontradas = df_bruto.columns.tolist()
                    
                    # Seletores
                    c1, c2, c3, c4 = st.columns(4)
                    col_venc = c1.selectbox("Vencimento", cols_encontradas, index=0)
                    col_num = c2.selectbox("Seu Número / NF", cols_encontradas, index=min(1, len(cols_encontradas)-1))
                    col_val = c3.selectbox("Valor (R$)", cols_encontradas, index=min(2, len(cols_encontradas)-1))
                    col_pag = c4.selectbox("Pagador / Cliente", cols_encontradas, index=min(3, len(cols_encontradas)-1))
                    
                    st.dataframe(df_bruto.head(3), hide_index=True) # Preview

                    if st.button("💾 Processar e Salvar no Banco", type="primary"):
                        mapa = {'vencimento': col_venc, 'numero': col_num, 'valor': col_val, 'pagador': col_pag}
                        
                        dados_processados = processar_dataframe_mapeado(df_bruto, mapa)
                        
                        # Salva e verifica cadastro
                        count_novos = 0
                        clientes_sem_cadastro = []
                        
                        for t in dados_processados:
                            salvar_dados_no_banco([t], conf['empresa_cnpj'])
                            if not mgr.verificar_cliente_existe(t['pagador']):
                                clientes_sem_cadastro.append(t['pagador'])
                        
                        # Feedback
                        st.success(f"{len(dados_processados)} títulos importados!")
                        
                        if clientes_sem_cadastro:
                            st.warning(f"⚠️ {len(set(clientes_sem_cadastro))} clientes novos precisam de cadastro na aba 'Clientes'.")
                            st.session_state.pendencia_cadastro = list(set(clientes_sem_cadastro))

    # --- ABA 2: COBRANÇA ---
    with t2:
        rel = mgr.agrupar_debitos_por_cliente()
        if not rel: st.success("Nada pendente.")
        else:
            for cli, info in rel.items():
                with st.expander(f"🔴 {cli} - Total: R$ {info['total']:,.2f}"):
                    st.dataframe(pd.DataFrame(info['detalhes']), use_container_width=True)
                    
                    # Botão para buscar PDF nos enviados
                    if st.button(f"📧 Buscar PDF no Enviados (NF {info['itens'][0]})", key=f"src_{cli}"):
                         sc = MailScanner(conf)
                         with st.spinner("Buscando no E-mail Enviado..."):
                             # Busca pela primeira NF pendente
                             res = sc.buscar_nf_enviada(info['itens'][0])
                             if res: st.success("PDF encontrado e baixado!")
                             else: st.error("PDF não encontrado nos itens enviados.")

                    msg = st.text_area("Mensagem WhatsApp", f"Olá {cli}, constam pendências de R$ {info['total']}.", key=f"t_{cli}")
                    if st.button("Enviar 🚀", key=f"z_{cli}"):
                        if mgr.enviar_cobranca_multipla(cli, msg, info['itens']):
                            salvar_log_envio(cli, 'WhatsApp', msg, 'Sucesso')
                            salvar_chat_whatsapp(cli, 'Bot', msg) # Salva no chat
                            st.toast("Enviado!")

    # --- ABA 3: CLIENTES (CRM COMPLETO) ---
    with t3:
        st.subheader("Gestão de Clientes")
        
        # Alerta de cadastros pendentes (vindos do PDF)
        pendentes = st.session_state.get('pendencia_cadastro', [])
        if pendentes:
            st.info(f"📝 Detectamos {len(pendentes)} novos clientes nos boletos. Cadastre-os abaixo:")
            sel_pendente = st.selectbox("Selecionar Pendente", ["-- Selecione --"] + pendentes)
            val_nome = sel_pendente if sel_pendente != "-- Selecione --" else ""
        else:
            val_nome = ""

        # Área de Cadastro / Edição
        with st.form("frm_cli"):
            col_a, col_b, col_c = st.columns(3)
            nm = col_a.text_input("Nome / Razão Social", value=val_nome)
            cn = col_b.text_input("CNPJ")
            zp = col_c.text_input("WhatsApp (55...)")
            em = st.text_input("E-mail")
            
            if st.form_submit_button("💾 Salvar Cliente"):
                mgr.cadastrar_cliente_completo(nm, cn, zp, em)
                if nm in pendentes: pendentes.remove(nm) # Remove da pendencia
                st.success("Salvo!")
                st.rerun()

        st.divider()
        
        # VISÃO 360 DO CLIENTE
        all_clis = listar_clientes_db()
        if all_clis:
            cli_view = st.selectbox("🔍 Ver Detalhes do Cliente:", [c['nome'] for c in all_clis])
            
            if cli_view:
                c_data = next(c for c in all_clis if c['nome'] == cli_view)
                
                tab_inf, tab_hist, tab_chat = st.tabs(["📋 Dados", "📜 Histórico Débitos", "💬 Chat Log"])
                
                with tab_inf:
                    st.write(f"**CNPJ:** {c_data['cnpj']}")
                    st.write(f"**Whats:** {c_data['whatsapp']}")
                    st.write(f"**Email:** {c_data['email']}")
                    if st.button("🗑️ Excluir Cliente"):
                        excluir_cliente_db(c_data['id'])
                        st.rerun()

                with tab_hist:
                    # Filtro de débitos (Simulado com Logs de Envio por enquanto)
                    logs = listar_logs_cliente(cli_view)
                    if logs:
                        st.dataframe(pd.DataFrame(logs)[['data_envio','tipo','status']], use_container_width=True)
                    else:
                        st.info("Nenhum envio registrado.")

                with tab_chat:
                    st.write("Histórico de Conversas (WhatsApp):")
                    chats = listar_chat_cliente(cli_view)
                    for chat in chats:
                        role = "chat-bot" if chat['remetente'] in ['Bot', 'Atendente'] else "chat-cliente"
                        icon = "🤖" if role == "chat-bot" else "👤"
                        st.markdown(f"""
                        <div class="chat-row {role}">
                            <strong>{icon} {chat['remetente']}</strong> <small>({chat['data_hora']})</small><br>
                            {chat['mensagem']}
                        </div>
                        """, unsafe_allow_html=True)
                    
                    # Simulação de envio manual de msg no chat
                    txt_chat = st.text_input("Nova mensagem manual:")
                    if st.button("Registrar/Enviar"):
                        salvar_chat_whatsapp(cli_view, 'Atendente', txt_chat)
                        st.rerun()

    # --- ABA 4: RELATÓRIOS ---
    with t4:
        st.subheader("Relatórios Gerais")
        st.info("Em breve: Gráficos de inadimplência e conversão.")

# ==============================================================================
# 2. GESTÃO
# ==============================================================================
elif selected == "Gestão":
    gt1, gt2 = st.tabs(["⚙️ Empresa Atual", "🏢 Minha Rede"])
    
    with gt1:
        if conf.get('empresa_cnpj'):
            st.subheader(f"Editando: {conf['empresa_nome']}")
            if st.button("✏️ Editar Configurações"):
                st.session_state.novo_cadastro = True
                st.rerun()
            if st.button("🗑️ Excluir Empresa", type="primary"):
                 if conf.get('id') and excluir_unidade_db(conf['id']):
                    st.session_state.config = {}
                    st.rerun()
    
    with gt2:
        unidades = carregar_todas_unidades_db()
        cols = st.columns(3)
        for u in unidades:
            with cols[0]: # Layout simples em coluna única pra teste
                 with st.container(border=True):
                    logo_html = renderizar_logo(u.get('logo_b64'), 50)
                    st.markdown(f"{logo_html} **{u['empresa_nome']}**", unsafe_allow_html=True)
                    if st.button("Entrar", key=f"ent_{u['id']}"):
                        st.session_state.config = u
                        st.rerun()
        if st.button("➕ Nova Empresa"):
            st.session_state.novo_cadastro = True
            st.session_state.config = {}
            st.rerun()

# ==============================================================================
# 3. CONFIG & SAIR
# ==============================================================================
elif selected == "Configurações":
    st.write("Alterar Senha Admin...")
    # (Mesmo código de alterar senha anterior)

elif selected == "Sair":
    st.session_state.logged_in = False
    st.session_state.config = {}
    st.rerun()

# ==============================================================================
# WIZARD DE CADASTRO (MANTIDO)
# ==============================================================================
if st.session_state.get('novo_cadastro', False):
    # Cole aqui o código do Wizard que te passei anteriormente (Abas 1, 2, 3)
    # Importante manter para poder editar/criar empresas.
    st.info("Wizard de Cadastro Aberto (Adicione o código aqui)")
    if st.button("Fechar Wizard"):
        st.session_state.novo_cadastro = False
        st.rerun()