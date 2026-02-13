import streamlit as st
import os
import time
import base64
import pandas as pd
from dotenv import load_dotenv
from streamlit_option_menu import option_menu
import datetime 
from google import genai
import holidays

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

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Credos SaaS", page_icon="🛡️", layout="wide", initial_sidebar_state="collapsed")
inicializar_banco()

# --- ESTILOS CSS ---
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

# --- FUNÇÕES VISUAIS ---
def testar_conexao_email(email, senha, imap_srv, smtp_srv):
    import smtplib
    import imaplib
    if not email or not senha or not imap_srv or not smtp_srv:
        return False, "Preencha todos os campos (Email, Senha, IMAP e SMTP) antes de testar."
    
    try:
        # 1. Testando recebimento (IMAP - Porta padrão SSL 993)
        imap = imaplib.IMAP4_SSL(imap_srv, 993)
        imap.login(email, senha)
        imap.logout()
        
        # 2. Testando envio (SMTP - Porta padrão SSL 465)
        smtp = smtplib.SMTP_SSL(smtp_srv, 465)
        smtp.login(email, senha)
        smtp.quit()
        
        return True, "Conexão de Envio (SMTP) e Recebimento (IMAP) bem-sucedidas! ✅"
    except Exception as e:
        return False, f"Falha na conexão: {str(e)}"
    
def renderizar_avatar_gmail(nome, logo_b64):
    if logo_b64: return f'<img src="data:image/png;base64,{logo_b64}" class="gmail-avatar-img" title="{nome}">'
    iniciais = "".join([n[0] for n in nome.split()[:2]]).upper() if nome else "US"
    return f'<div class="gmail-avatar-text" title="{nome}">{iniciais}</div>'

def renderizar_logo(b64_string, tamanho=50):
    if b64_string: return f'<img src="data:image/png;base64,{b64_string}" style="width:{tamanho}px; height:{tamanho}px; border-radius:50%; vertical-align:middle; border:2px solid #eee;">'
    return "🏢"

# --- LOGIN ---
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

def ativar_empresa(nova_config):
    st.session_state.config = nova_config
    st.session_state.ir_para_gestao = False

if not st.session_state.logged_in:
    c1, c2, c3 = st.columns([1,1,1])
    with c2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.title("🛡️ Credos System")
        with st.form("login_form"):
            st.text_input("Usuário", key="u_input")
            st.text_input("Senha", type="password", key="p_input")
            st.form_submit_button("Entrar", on_click=fazer_login)
    st.stop()

# --- INICIALIZAÇÃO E CARGA DE CONFIGURAÇÕES ---
# 1. Garante que a chave 'config' sempre exista na memória para evitar erros de Atributo
if 'config' not in st.session_state:
    st.session_state.config = {}

# 2. Se o usuário estiver logado e a memória estiver vazia (pós-F5), recarrega do banco
if st.session_state.get('logged_in'):
    if not st.session_state.config:
        dados_do_banco = carregar_configuracoes_db()
        if dados_do_banco:
            st.session_state.config = dados_do_banco
        else:
            st.session_state.config = {}

# 3. Define a variável 'conf' de forma segura (sempre no singular 'config')
# O .get() evita que o sistema quebre caso a chave suma por um milisegundo
conf = st.session_state.get('config', {})

# Sobrescreve com ENV se existir (Segurança)
if os.getenv("EVO_API_URL"): st.session_state.config['evo_url'] = os.getenv("EVO_API_URL")
if os.getenv("EVO_GLOBAL_KEY"): st.session_state.config['evo_key'] = os.getenv("EVO_GLOBAL_KEY")
if os.getenv("GEMINI_API_KEY"): st.session_state.config['gemini_api_key'] = os.getenv("GEMINI_API_KEY")

mgr = Manager(conf['empresa_cnpj']) if conf.get('empresa_cnpj') else None

if not conf.get('empresa_cnpj') and 'novo_cadastro' not in st.session_state:
    st.session_state.novo_cadastro = True

# --- HEADER SUPERIOR ---
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

# --- MENU DE NAVEGAÇÃO ---
idx_padrao = 1 if st.session_state.get('ir_para_gestao') else 0
if st.session_state.get('ir_para_gestao'): st.session_state.ir_para_gestao = False

# ⚡ ATUALIZAÇÃO 1: Adicionado o "Atendimento" no menu
selected = option_menu(
    menu_title=None, options=["Operacional", "Atendimento", "Gestão", "Configurações"],
    icons=["hdd-stack", "chat-dots", "building-gear", "sliders"], default_index=idx_padrao, orientation="horizontal",
    styles={"container": {"padding": "0!important", "background-color": "#f8f9fa"}}
)

# ==============================================================================
# ÁREA OPERACIONAL
# ==============================================================================
if selected == "Operacional":
    if not mgr:
        st.warning("⚠️ Nenhuma empresa selecionada. Vá em Gestão e selecione uma unidade.")
        st.stop()
    
    t1, t2, t3, t4, t5 = st.tabs(["📂 Importar PDF", "📝 Lançar Manual", "💸 Cobrança (Envio)", "👥 CRM & Carteira", "📊 Relatórios"])

    # --- ABA 1: IMPORTAÇÃO ---
    with t1:
        layouts_salvos = mgr.obter_layouts_bancos()
        st.markdown("##### ⚡ Selecione o Banco para Importar")
        cols_bancos = st.columns(4)
        
        if 'layout_ativo' not in st.session_state: st.session_state.layout_ativo = None
        if 'modo_novo_layout' not in st.session_state: st.session_state.modo_novo_layout = False
        
        # Botão para criar novo banco sempre na primeira coluna
        if cols_bancos[0].button("➕ Novo Banco...", use_container_width=True):
            st.session_state.layout_ativo = None
            st.session_state.modo_novo_layout = True
            st.rerun()
            
        # Loop para renderizar os bancos existentes
        for i, layout in enumerate(layouts_salvos):
            col_idx = (i + 1) % 4
            id_layout = layout.get('id')
            nome_layout = layout['nome_layout']
            
            with cols_bancos[col_idx]:
                # Botão de Selecionar
                if st.button(f"🏦 {nome_layout}", key=f"sel_{id_layout}", use_container_width=True):
                    st.session_state.layout_ativo = layout
                    st.session_state.modo_novo_layout = False
                    st.rerun()
                
                # Botão de Excluir (Adicionado aqui)
                if st.button(f"🗑️ Excluir", key=f"del_{id_layout}", type="secondary", use_container_width=True):
                    from src.database import excluir_layout
                    
                    if excluir_layout(id_layout):
                        st.toast(f"Banco {nome_layout} excluído!")
                        
                        # PROTEÇÃO: Verificamos se existe algo em layout_ativo antes de dar o .get()
                        layout_atual = st.session_state.get('layout_ativo')
                        if layout_atual is not None:
                            if layout_atual.get('id') == id_layout:
                                st.session_state.layout_ativo = None
                        
                        time.sleep(0.5)
                        st.rerun() 
                    else:
                        st.error("Erro ao excluir do banco de dados.")
                    
                    # Botão pequeno para excluir o layout
                    if st.button(f"🗑️ Excluir", key=f"btn_del_{id_layout}", use_container_width=True, type="secondary"):
                        # Chama a função de exclusão no manager (deve ser criada no manager.py/database.py)
                        def excluir_layout_banco(self, id_layout):
                         from src.database import excluir_layout
                         return excluir_layout(id_layout)

        st.divider()
        
        # 2. Área de Configuração de Novo Layout
        if st.session_state.modo_novo_layout:
            st.info("🆕 Configurando um novo padrão.")
            nome_novo_banco = st.text_input("Nome do Banco", key="input_nome_banco")
            up_pdf = st.file_uploader("Upload do PDF para Mapear", type="pdf", key="uploader_mapeamento")
            
            if up_pdf:
                df_bruto = ler_pdf_bruto(up_pdf)
                if df_bruto is not None:
                    st.write("### 🔍 Prévia dos Dados Identificados")
                    st.dataframe(df_bruto.head(10), use_container_width=True)
                    
                    cols = df_bruto.columns.tolist()
                    st.write("### 🗺️ Mapeamento de Colunas")
                    
                    c1, c2, c3, c4 = st.columns(4)
                    # Adicionamos chaves únicas para os selectboxes
                    col_venc = c1.selectbox("Vencimento", cols, key="sel_venc")
                    col_num = c2.selectbox("Número/NF", cols, index=min(1, len(cols)-1), key="sel_num")
                    col_val = c3.selectbox("Valor", cols, index=min(2, len(cols)-1), key="sel_val")
                    col_pag = c4.selectbox("Cliente", cols, index=min(3, len(cols)-1), key="sel_pag")
                    
                    st.divider()
                    
                    # Botão de Salvar com chave única e lógica de persistência
                    if st.button("💾 Salvar Layout", type="primary", key="btn_salvar_layout_novo"):
                        if nome_novo_banco:
                            mapa = {
                                'vencimento': col_venc, 
                                'numero': col_num, 
                                'valor': col_val, 
                                'pagador': col_pag
                            }
                            # Chama o manager para salvar no banco
                            mgr.salvar_layout_preferido(nome_novo_banco, mapa)
                            st.success(f"Layout '{nome_novo_banco}' salvo com sucesso!")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("Por favor, digite o nome do banco antes de salvar.")

        elif st.session_state.layout_ativo:
            layout = st.session_state.layout_ativo
            st.markdown(f"### 📂 Importando: **{layout['nome_layout']}**")
            up_pdf_rapido = st.file_uploader("Arraste o PDF", type="pdf")
            if up_pdf_rapido:
                df_bruto = ler_pdf_bruto(up_pdf_rapido)
                if df_bruto is not None:
                    mapa_atual = {'vencimento': layout['col_vencimento'], 'numero': layout['col_numero'], 'valor': layout['col_valor'], 'pagador': layout['col_pagador']}
                    dados_processados = processar_dataframe_mapeado(df_bruto, mapa_atual)
                    if st.button("🚀 Confirmar Importação", type="primary"):
                        for t in dados_processados: salvar_dados_no_banco([t], conf['empresa_cnpj'])
                        st.success("Importado!"); time.sleep(1); st.rerun()

    # --- ABA 2: MANUAL ---
    with t2:
        st.subheader("📝 Lançar Manualmente")
        lista_clientes = listar_clientes_db(conf['empresa_cnpj'])
        with st.form("form_manual"):
            c1, c2 = st.columns(2)
            cliente_sel = c1.selectbox("Cliente", [c['nome'] for c in lista_clientes] if lista_clientes else ["--"])
            nf_manual = c2.text_input("Número do Documento/NF")
            valor_manual = st.number_input("Valor (R$)", min_value=0.01)
            venc_manual = st.date_input("Vencimento")
            if st.form_submit_button("💾 Lançar"):
                venc_str = venc_manual.strftime("%d/%m/%Y")
                salvar_dados_no_banco([{'pagador': cliente_sel, 'numero': nf_manual, 'vencimento': venc_str, 'valor': valor_manual}], conf['empresa_cnpj'])
                st.success("Lançado!"); st.rerun()

    # --- ABA 3: COBRANÇA ---
    with t3:
        rel = mgr.agrupar_debitos_por_cliente()
        if rel:
            st.markdown(f"### 🚀 Fila: {len(rel)} clientes")
            for cli, info in rel.items():
                with st.expander(f"🔴 {cli} | R$ {info['total']:,.2f}"):
                    st.dataframe(pd.DataFrame(info['itens']))
                    if st.button(f"📧 Enviar Cobrança para {cli}", key=f"btn_{cli}", type="primary"):
                        msg = mgr.gerar_mensagem_cobranca(cli, info['dados_cliente'], info['total'], info['itens'])
                        zip_path, temp = mgr.buscar_e_zipar_pdfs(cli, info['itens'])
                        mgr.executar_processo_completo_cobranca(cli, msg, zip_path, info['itens'], temp)
                        st.success("Enviado!")

    # --- ABA 4: CRM ---
    with t4:
        st.subheader("👥 CRM & Carteira")
        all_clis = listar_clientes_db(conf['empresa_cnpj'])
        if all_clis:
            df_edit = st.data_editor(pd.DataFrame(all_clis), hide_index=True)
            if st.button("💾 Atualizar CRM"):
                for _, r in df_edit.iterrows(): mgr.cadastrar_cliente_completo(r['nome'], r['cnpj'], r['whatsapp'], r['email'])
                st.success("Atualizado!")

# ==============================================================================
# ÁREA DE ATENDIMENTO OMNICHANNEL (NOVO)
# ==============================================================================
elif selected == "Atendimento":
    st.markdown("## 💬 Atendimento Manual Humanizado")
    st.write("Envie mensagens individuais assinadas com o seu nome para os clientes.")
    st.divider()

    col_chat1, col_chat2 = st.columns([1, 2])

    with col_chat1:
        numero_cliente = st.text_input("WhatsApp do Cliente (Apenas números)", help="Exemplo: 5511999999999")

    with col_chat2:
        texto_da_tela = st.text_area("Mensagem:", height=150)

        if st.button("Enviar Mensagem 🚀", type="primary"):
            if numero_cliente and texto_da_tela:
                with st.spinner("Conectando ao WhatsApp..."):
                    # Puxa os dados da sessão 
                    # Lógica para tratar se usuario_atual é dicionário ou apenas o login
                    nome_empresa = conf.get('empresa_nome', 'Credos_SaaS')
                    if isinstance(st.session_state.usuario_atual, dict):
                        agente_logado = st.session_state.usuario_atual.get('nome_completo', 'Atendimento')
                    else:
                        agente_logado = str(st.session_state.usuario_atual).capitalize()

                    # Inicia a Evolution API
                    evo = EvolutionController(config=st.session_state.config, nome_empresa_cliente=nome_empresa)

                    # Formata a mensagem humanizada diretamente aqui
                    mensagem_final = f"*{agente_logado}*\n{texto_da_tela}"

                    # Dispara a mensagem
                    sucesso = evo.enviar_mensagem_texto(numero_cliente, mensagem_final)

                    if sucesso:
                        st.success("Mensagem entregue com sucesso no aparelho do cliente!")
                        # No futuro, chamada para o banco entra aqui:
                        # salvar_historico_chat(numero_cliente, agente_logado, texto_da_tela, "ENVIADO")
                    else:
                        st.error("Falha ao enviar. Verifique se o QR Code está conectado na aba Configurações.")
            else:
                st.warning("Preencha o número e a mensagem antes de enviar.")

# ==============================================================================
# GESTÃO
# ==============================================================================
elif selected == "Gestão":
    st.subheader("🏢 Unidades")
    unidades = carregar_todas_unidades_db()
    cols = st.columns(3)
    for i, u in enumerate(unidades):
        with cols[i % 3]:
            with st.container(border=True):
                st.markdown(f"**{u['empresa_nome']}**")
                st.button("Acessar", key=f"go_{u['id']}", on_click=ativar_empresa, args=(u,), use_container_width=True)

# ==============================================================================
# CONFIGURAÇÕES
# ==============================================================================
elif selected == "Configurações":
    ct1, ct2, ct3, ct4, ct5 = st.tabs(["🏠 Perfil", "👥 Usuários", "🟢 WhatsApp", "📧 E-mail", "🤖 IA & Automação"])
    
    with ct1:
        st.markdown("### 🏢 Dados da Unidade / Empresa")
        
        # Carregamos os dados da empresa que estão na sessão
        conf = st.session_state.get('config', {})
        
        col_logo_pref, col_info_pref = st.columns([1, 3])
        
        with col_logo_pref:
            logo_b64 = conf.get('logo_b64')
            if logo_b64:
                st.image(f"data:image/png;base64,{logo_b64}", width=150)
            else:
                st.info("Sem Logo")
            
            nova_logo = st.file_uploader("Trocar Logotipo", type=["png", "jpg"], label_visibility="collapsed")

        with col_info_pref:
            with st.form("form_perfil_empresa"):
                nome_f = st.text_input("Razão Social / Nome Fantasia", value=conf.get('empresa_nome', ''))
                cnpj_f = st.text_input("CNPJ", value=conf.get('empresa_cnpj', ''))
                
                if st.form_submit_button("💾 Salvar Dados da Empresa"):
                    updates = {"empresa_nome": nome_f, "empresa_cnpj": cnpj_f}
                    
                    if nova_logo:
                        import base64
                        b64_logo = base64.b64encode(nova_logo.read()).decode()
                        updates["logo_b64"] = b64_logo
                    
                    st.session_state.config.update(updates)
                    salvar_configuracoes_db(st.session_state.config)
                    st.success("Dados da empresa atualizados!")
                    st.rerun()

    with ct2:
        st.markdown("### 👥 Gestão de Usuários")
        
        # 1. CRIAR NOVO USUÁRIO
        with st.expander("➕ Cadastrar Novo Funcionário/Operador"):
            with st.form("novo_user_gestao"):
                c1, c2, c3 = st.columns(3)
                n_nome = c1.text_input("Nome Completo")
                n_login = c2.text_input("Login (E-mail)")
                n_pass = c3.text_input("Senha", type="password")
                
                c4, c5 = st.columns([1, 2])
                n_perfil = c4.selectbox("Nível de Acesso", ["operador", "admin"])
                n_foto = c5.file_uploader("Foto de Perfil (Opcional)", type=["png", "jpg", "jpeg"])
                
                if st.form_submit_button("Criar Usuário"):
                    if n_login and n_pass:
                        foto_b64 = None
                        if n_foto:
                            import base64
                            foto_b64 = base64.b64encode(n_foto.read()).decode()
                            
                        # Chama a função do banco
                        sucesso, msg = criar_usuario(n_login, n_pass, n_nome, n_perfil, foto_b64)
                        if sucesso:
                            st.success(msg)
                            time.sleep(1) # Pequena pausa para o banco processar
                            st.rerun()
                        else:
                            st.error(msg)
                    else:
                        st.warning("Preencha o Login e a Senha obrigatoriamente.")

        st.divider()
        st.markdown("#### 🔑 Usuários Ativos")

        # 2. LISTAGEM REAL (Ajustada para garantir a exibição)
        usuarios_do_banco = listar_usuarios()
        
        if not usuarios_do_banco:
            st.info("ℹ️ Nenhum usuário cadastrado além do administrador principal.")
        else:
            for i, u in enumerate(usuarios_do_banco):
                # Extração segura de dados
                u_login = u.get('login') or f"user_{i}"
                u_nome = u.get('nome_completo') or "Sem Nome"
                u_perfil = u.get('perfil', 'operador')
                u_foto = u.get('foto_b64')

                with st.container(border=True):
                    c_foto, c_dados, c_edit, c_del = st.columns([1, 3, 1, 1])
                    
                    with c_foto:
                        if u_foto:
                            st.image(f"data:image/png;base64,{u_foto}", width=50)
                        else:
                            st.markdown("### 👤")

                    with c_dados:
                        st.write(f"**{u_nome}**")
                        st.caption(f"Login: {u_login} | Perfil: {u_perfil.upper()}")
                    
                    with c_edit:
                        with st.popover("📝 Editar"):
                            new_nome = st.text_input("Nome", value=u_nome, key=f"edit_n_{u_login}")
                            perf_lista = ["operador", "admin"]
                            idx_perf = perf_lista.index(u_perfil) if u_perfil in perf_lista else 0
                            new_perf = st.selectbox("Perfil", perf_lista, index=idx_perf, key=f"edit_p_{u_login}")
                            
                            st.divider()
                            if st.button("🔑 Resetar Senha (123456)", key=f"reset_{u_login}"):
                                redefinir_senha_usuario(u_login)
                                st.success("Senha resetada!")
                            
                            if st.button("Salvar Alterações", key=f"save_{u_login}", type="primary"):
                                atualizar_usuario_db(u_login, new_nome, new_perf)
                                st.success("Atualizado!")
                                st.rerun()
                    
                    with c_del:
                        if st.button("🗑️", key=f"del_{u_login}", help="Excluir Usuário"):
                            excluir_usuario(u_login)
                            st.rerun()
    with ct3:
        st.markdown("### 🟢 WhatsApp (Conexão do Aparelho)")
        st.write("Conecte seu WhatsApp para habilitar o robô de disparo.")
        st.divider()

        nome_instancia = conf.get('empresa_cnpj', 'Instancia_Padrao').replace('.', '').replace('/', '').replace('-', '')
        evo = EvolutionController(config=st.session_state.config, nome_empresa_cliente=nome_instancia)
        
        with st.spinner("Verificando status..."):
            status_conexao = evo.checar_status()

        col_status, col_acao = st.columns([2, 1])
        
        with col_status:
            if status_conexao == "open":
                st.success("✅ **Status: Conectado!** Seu WhatsApp está pronto.")
            elif status_conexao == "connecting":
                st.warning("⏳ **Status: Conectando...** Aguarde no seu celular.")
            elif status_conexao == "config_error":
                 st.error("❌ Erro interno: Chave global ou URL do servidor ausentes.")
            else:
                st.error("❌ **Status: Desconectado.** Escaneie o QR Code para conectar.")

        with col_acao:
            if status_conexao == "open":
                if st.button("🔌 Desconectar WhatsApp", type="primary"):
                    evo.deletar_instancia() 
                    st.session_state.mostrar_qr = False
                    st.rerun()
            else:
                if st.button("🔄 Gerar QR Code"):
                    with st.spinner("Criando servidor do WhatsApp..."):
                        res_criacao = evo.criar_instancia()
                        
                        if "error" in res_criacao and "already exists" not in str(res_criacao).lower():
                            st.error(f"Erro na Evolution: {res_criacao['error']}")
                        else:
                            st.session_state.mostrar_qr = True
                            st.rerun()

        if st.session_state.get('mostrar_qr') and status_conexao != "open":
            st.markdown("---")
            st.markdown("#### 📱 Escaneie para Conectar")
            
            if st.button("♻️ Resetar Instância (Tente se o QR não aparecer)"):
                evo.deletar_instancia()
                st.session_state.mostrar_qr = False
                st.rerun()

            with st.spinner("Solicitando QR Code ao servidor..."):
                import time
                time.sleep(3) 
                qr_data = evo.buscar_qrcode()
                
                if qr_data:
                    st.image(qr_data, width=300, caption="O QR Code expira em 30 segundos")
                    st.info("💡 Após escanear, aguarde a mensagem de 'Conectado' aparecer no celular e recarregue esta aba.")
                    if st.button("🔄 Já escaneei, atualizar status"):
                        st.session_state.mostrar_qr = False
                        st.rerun()
                else:
                    st.error("Não foi possível gerar o QR Code. Verifique se o servidor Evolution está online em: " + evo.url)
                    
    with ct4:
        st.markdown("### 📧 E-mail")
        conf = st.session_state.get('config', {})

        # --- BLOCO DO FORMULÁRIO (Apenas para SALVAR) ---
        with st.form("mail_cfg"):
            st.markdown("#### ⚙️ Servidores de E-mail")
            c_srv1, c_srv2 = st.columns(2)
            imap_server = c_srv1.text_input("Servidor IMAP (Receber)", value=conf.get('imap_server', 'imap.gmail.com'))
            smtp_server = c_srv2.text_input("Servidor SMTP (Enviar)", value=conf.get('smtp_server', 'smtp.gmail.com'))

            st.markdown("#### 👤 Contas do Sistema")
            c1, c2 = st.columns(2)
            b_u = c1.text_input("Email Base", value=conf.get('base_mail_user', ''))
            b_p = c1.text_input("Senha Base", type="password", value=conf.get('base_mail_pass', ''))
            
            f_u = c2.text_input("Email Financeiro", value=conf.get('fin_mail_user', ''))
            f_p = c2.text_input("Senha Financeira", type="password", value=conf.get('fin_mail_pass', ''))
            
            # Único botão permitido dentro do form
            btn_salvar = st.form_submit_button("💾 Salvar Configurações")
            
            if btn_salvar:
                updates = {
                    "imap_server": imap_server, "smtp_server": smtp_server,
                    "base_mail_user": b_u, "base_mail_pass": b_p, 
                    "fin_mail_user": f_u, "fin_mail_pass": f_p
                }
                salvar_configuracoes_db(updates)
                st.session_state.config.update(updates)
                st.success("Configurações salvas!")
                time.sleep(1)
                st.rerun()

        # --- BLOCO DE TESTE (FORA do st.form) ---
        st.divider()
        st.markdown("#### 🔌 Testar Conexões")
        st.caption("Salve as configurações antes de testar.")
        
        col_btn1, col_btn2 = st.columns(2)
        
        # Agora os botões funcionam porque não estão mais "presos" no formulário
        if col_btn1.button("🧪 Testar Email Base", use_container_width=True):
            if b_u and b_p:
                with st.spinner("Testando Base..."):
                    sucesso, msg = testar_conexao_email(b_u, b_p, imap_server, smtp_server)
                    if sucesso: st.success(msg)
                    else: st.error(msg)
            else:
                st.warning("Preencha os dados do Email Base.")

        if col_btn2.button("🧪 Testar Email Financeiro", use_container_width=True):
            if f_u and f_p:
                with st.spinner("Testando Financeiro..."):
                    sucesso, msg = testar_conexao_email(f_u, f_p, imap_server, smtp_server)
                    if sucesso: st.success(msg)
                    else: st.error(msg)
            else:
                st.warning("Preencha os dados do Email Financeiro.")

    with ct5:
        st.markdown("### 🤖 Cérebro (IA)")
        ag = mgr.obter_agendamento() if mgr else {}
        
        with st.form("form_robo"):
            with st.expander("❓ Como gerar a API Key?"):
                st.markdown("1. Acesse o Google Cloud e habilite o Faturamento.\n2. Ative a **Generative Language API**.\n3. Crie e copie sua credencial.")

            gemini_key = st.text_input("API Key Gemini", value=conf.get('gemini_api_key', ''), type="password")
            
            st.divider()
            st.markdown("#### ⚙️ Regras de Agendamento")
            
            c_on = st.toggle("Ativar Robô de Envio", value=ag.get('ativo', False) if ag else False)
            
            dias_sel = st.multiselect(
                "Dias da semana:", 
                ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"], 
                default=ag.get('dias_ui', ["Segunda", "Terça", "Quarta", "Quinta", "Sexta"]) if ag else ["Segunda"]
            )
            
            col_hora, col_feriado = st.columns(2)
            
            with col_hora:
                hora_str = ag.get('hora_envio', "09:00") if ag else "09:00"
                try:
                    hora_padrao = datetime.datetime.strptime(hora_str, "%H:%M").time()
                except ValueError:
                    hora_padrao = datetime.time(9, 0)
                hora_envio = st.time_input("Horário do disparo:", value=hora_padrao)
                
            with col_feriado:
                st.write("")
                st.write("")
                ignorar_feriados = st.checkbox(
                    "Pausar em Feriados", 
                    value=ag.get('ignorar_feriados', True) if ag else True,
                    help="O robô não fará envios em feriados nacionais."
                )
            
            if st.form_submit_button("💾 Salvar IA"):
                st.session_state.config.update({"gemini_api_key": gemini_key})
                salvar_configuracoes_db(st.session_state.config)
                hora_formatada = hora_envio.strftime("%H:%M")
                mgr.salvar_config_agendamento(dias_sel, hora_formatada, ignorar_feriados, c_on)
                st.success("Configuração salva com sucesso!"); st.rerun()
        
        st.divider()
        col_test, col_res = st.columns([1, 3])
        if col_test.button("🧠 Testar Cérebro"):
            k_test = st.session_state.config.get('gemini_api_key')
            if not k_test:
                col_res.warning("⚠️ Insira e salve a chave primeiro.")
            else:
                with st.spinner("Conectando com o Google..."):
                    try:
                        from google import genai
                        client = genai.Client(api_key=k_test)
                        response = client.models.generate_content(
                            model='gemini-2.0-flash-lite', 
                            contents="Diga: SISTEMA IA ONLINE"
                        )
                        col_res.success(f"🤖 {response.text}")
                    except Exception as e:
                        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                            col_res.info("ℹ️ Cota excedida (429). Simulação Ativa.")
                            col_res.success("🤖 (SIMULADO): SISTEMA IA ONLINE")
                        else:
                            col_res.error(f"Erro: {e}")
# --- WIZARD NOVO CADASTRO ---
if st.session_state.get('novo_cadastro', False):
    st.markdown("---")
    with st.form("wiz"):
        st.subheader("🧙‍♂️ Nova Empresa")
        n = st.text_input("Nome Fantasia")
        c = st.text_input("CNPJ")
        if st.form_submit_button("Salvar Empresa"):
            st.session_state.config.update({"empresa_nome": n, "empresa_cnpj": c})
            salvar_configuracoes_db(st.session_state.config)
            st.session_state.novo_cadastro = False; st.rerun()