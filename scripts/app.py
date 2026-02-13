import streamlit as st
import os
import time
import base64
import pandas as pd
from dotenv import load_dotenv
from streamlit_option_menu import option_menu
import datetime 

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
            st.form_submit_button("Entrar", on_click=fazer_login, width="stretch")
    st.stop()

# --- CARREGA CONFIGURAÇÕES ---
if 'config' not in st.session_state or not st.session_state.config: 
    st.session_state.config = carregar_configuracoes_db() or {}
conf = st.session_state.config

# Sobrescreve com ENV se existir (Segurança)
if os.getenv("EVO_API_URL"): st.session_state.config['evo_url'] = os.getenv("EVO_API_URL")
if os.getenv("EVO_GLOBAL_KEY"): st.session_state.config['evo_key'] = os.getenv("EVO_GLOBAL_KEY")
if os.getenv("GEMINI_API_KEY"): st.session_state.config['gemini_key'] = os.getenv("GEMINI_API_KEY")

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
        if st.button("🔄 Trocar Empresa", width="stretch"):
            st.session_state.ir_para_gestao = True
            st.rerun()
        if st.button("🚪 Sair", type="primary", width="stretch"): fazer_logout()

st.divider()

# --- MENU DE NAVEGAÇÃO ---
idx_padrao = 1 if st.session_state.get('ir_para_gestao') else 0
if st.session_state.get('ir_para_gestao'): st.session_state.ir_para_gestao = False

selected = option_menu(
    menu_title=None, options=["Operacional", "Gestão", "Configurações"],
    icons=["hdd-stack", "building-gear", "sliders"], default_index=idx_padrao, orientation="horizontal",
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

    # --- ABA 1: IMPORTAÇÃO INTELIGENTE ---
    with t1:
        # Busca layout direto do banco
        layouts_salvos = mgr.obter_layouts_bancos()
        
        st.markdown("##### ⚡ Selecione o Banco para Importar")
        cols_bancos = st.columns(4)
        if 'layout_ativo' not in st.session_state: st.session_state.layout_ativo = None
        if 'modo_novo_layout' not in st.session_state: st.session_state.modo_novo_layout = False
        
        # Botão Novo Layout
        if cols_bancos[0].button("➕ Novo Banco...", width="stretch"):
            st.session_state.layout_ativo = None
            st.session_state.modo_novo_layout = True
            
        # Botões de Bancos Salvos (Gera dinamicamente)
        for i, layout in enumerate(layouts_salvos):
            col_idx = (i + 1) % 4
            if cols_bancos[col_idx].button(f"🏦 {layout['nome_layout']}", width="stretch"):
                st.session_state.layout_ativo = layout
                st.session_state.modo_novo_layout = False
        st.divider()
        
        # MODO 1: CRIAR NOVO LAYOUT
        if st.session_state.modo_novo_layout:
            st.info("🆕 Configurando um novo padrão.")
            nome_novo_banco = st.text_input("Nome do Banco", placeholder="Ex: Itaú")
            up_pdf = st.file_uploader("Upload do PDF para Mapear", type="pdf", key="up_novo")
            if up_pdf:
                df_bruto = ler_pdf_bruto(up_pdf)
                if df_bruto is not None:
                    st.markdown("###### 👀 Visualização dos Dados:")
                    st.dataframe(df_bruto.head(10), width="stretch")
                    st.divider()

                    st.markdown("###### Mapeie as colunas:")
                    cols = df_bruto.columns.tolist()
                    c1, c2, c3, c4 = st.columns(4)
                    col_venc = c1.selectbox("Vencimento", cols)
                    col_num = c2.selectbox("Número/NF", cols, index=min(1, len(cols)-1))
                    col_val = c3.selectbox("Valor", cols, index=min(2, len(cols)-1))
                    col_pag = c4.selectbox("Cliente", cols, index=min(3, len(cols)-1))
                    
                    if st.button("💾 Salvar Layout", type="primary"):
                        if nome_novo_banco:
                            mapa = {'vencimento': col_venc, 'numero': col_num, 'valor': col_val, 'pagador': col_pag}
                            mgr.salvar_layout_preferido(nome_novo_banco, mapa)
                            st.success(f"Banco '{nome_novo_banco}' salvo!")
                            time.sleep(1.5); st.session_state.modo_novo_layout = False; st.rerun()
                        else: st.error("Digite um nome.")

        # MODO 2: USAR LAYOUT EXISTENTE
        elif st.session_state.layout_ativo:
            layout = st.session_state.layout_ativo
            st.markdown(f"### 📂 Importando: **{layout['nome_layout']}**")
            if st.button("🗑️ Excluir modelo", type="secondary"):
                mgr.excluir_layout(layout['id']); st.session_state.layout_ativo = None; st.rerun()
            
            up_pdf_rapido = st.file_uploader(f"Arraste o PDF do {layout['nome_layout']}", type="pdf", key="up_rapido")
            if up_pdf_rapido:
                with st.spinner("Processando..."):
                    df_bruto = ler_pdf_bruto(up_pdf_rapido)
                if df_bruto is not None:
                    with st.expander("👀 Ver dados brutos"): st.dataframe(df_bruto.head(5))
                    cols = df_bruto.columns.tolist()
                    def safe_idx(nome_col): return cols.index(nome_col) if nome_col in cols else 0
                    
                    with st.expander("🔧 Ajustar Colunas (Se necessário)"):
                        c1, c2, c3, c4 = st.columns(4)
                        col_venc = c1.selectbox("Vencimento", cols, index=safe_idx(layout['col_vencimento']))
                        col_num = c2.selectbox("Número/NF", cols, index=safe_idx(layout['col_numero']))
                        col_val = c3.selectbox("Valor", cols, index=safe_idx(layout['col_valor']))
                        col_pag = c4.selectbox("Cliente", cols, index=safe_idx(layout['col_pagador']))
                    
                    mapa_atual = {'vencimento': col_venc, 'numero': col_num, 'valor': col_val, 'pagador': col_pag}
                    dados_processados = processar_dataframe_mapeado(df_bruto, mapa_atual)
                    
                    clientes_novos = list(set([d['pagador'] for d in dados_processados if not mgr.verificar_cliente_existe(d['pagador'])]))
                    df_editor_novos = None
                    if clientes_novos:
                        st.warning(f"⚠️ {len(clientes_novos)} clientes novos.")
                        df_novos = pd.DataFrame([{"nome": c, "cnpj":"", "whatsapp":"", "email":"", "contato":""} for c in clientes_novos])
                        df_editor_novos = st.data_editor(df_novos, hide_index=True, key="edit_novos_fast")
                    else: st.success("✅ Todos os clientes já cadastrados.")
                    
                    if st.button("🚀 Confirmar Importação", type="primary", width="stretch"):
                        if df_editor_novos is not None:
                            for _, row in df_editor_novos.iterrows(): 
                                mgr.cadastrar_cliente_completo(row['nome'], row['cnpj'], row['whatsapp'], row['email'], row['contato'])
                        for t in dados_processados: 
                            salvar_dados_no_banco([t], conf['empresa_cnpj'])
                        st.success(f"{len(dados_processados)} títulos importados."); time.sleep(2); st.rerun()
        else: st.info("👈 Selecione um banco acima.")

    # --- ABA 2: LANÇAMENTO MANUAL ---
    with t2:
        st.subheader("📝 Lançar Manualmente")
        lista_clientes = listar_clientes_db(conf['empresa_cnpj'])
        nomes_cli = [c['nome'] for c in lista_clientes]
        with st.form("form_manual"):
            c1, c2 = st.columns(2)
            opcoes_cli = nomes_cli if nomes_cli else ["-- Nenhum Cliente Cadastrado --"]
            cliente_sel = c1.selectbox("Cliente", opcoes_cli)
            nf_manual = c2.text_input("Número do Documento/NF")
            c3, c4 = st.columns(2)
            valor_manual = c3.number_input("Valor (R$)", min_value=0.01, step=10.0)
            venc_manual = c4.date_input("Data de Vencimento")
            obs_manual = st.text_area("Observação")
            if st.form_submit_button("💾 Lançar Título"):
                if cliente_sel and cliente_sel != "-- Nenhum Cliente Cadastrado --" and nf_manual:
                    venc_str = venc_manual.strftime("%d/%m/%Y")
                    dados_titulo = [{'pagador': cliente_sel, 'numero': nf_manual, 'vencimento': venc_str, 'valor': valor_manual}]
                    salvar_dados_no_banco(dados_titulo, conf['empresa_cnpj'])
                    st.success("Lançado!"); time.sleep(1); st.rerun()
                else: st.error("Erro.")

    # --- ABA 3: COBRANÇA (ENVIO) ---
    with t3:
        # Filtro de Busca
        col_filtro, _ = st.columns([1, 1])
        filtro_cobranca = col_filtro.text_input("🔍 Filtrar Devedor (Nome)", placeholder="Digite o nome para buscar...")
        
        st.caption("Fila de disparo.")
        rel = mgr.agrupar_debitos_por_cliente()
        
        if filtro_cobranca: 
            rel = {k: v for k, v in rel.items() if filtro_cobranca.lower() in k.lower()}
            
        if rel:
             c_head1, c_head2 = st.columns([3, 1])
             c_head1.markdown(f"### 🚀 Fila: {len(rel)} clientes")
             
             if not filtro_cobranca:
                 if c_head2.button("🔥 DISPARAR PARA TODOS", type="primary", key="btn_mass_send"):
                     st.toast("Iniciando motor...")
                     progresso = st.progress(0)
                     status_text = st.empty()
                     log_container = st.container(height=200, border=True)
                     total_clientes = len(rel)
                     for i, (cli_nome, info) in enumerate(rel.items()):
                         progresso.progress((i) / total_clientes)
                         status_text.write(f"🔄 **{i+1}/{total_clientes}**: {cli_nome}...")
                         try:
                             msg_massa = mgr.gerar_mensagem_cobranca(cli_nome, info['dados_cliente'], info['total'], info['itens'])
                             log_container.write(f"📂 {cli_nome}: Preparando arquivos...")
                             zip_path, arquivos_temp = mgr.buscar_e_zipar_pdfs(cli_nome, info['itens'])
                             
                             log_container.write(f"📨 {cli_nome}: Enviando...")
                             res = mgr.executar_processo_completo_cobranca(cli_nome, msg_massa, zip_path, info['itens'], arquivos_temp)
                             
                             status_icon = "✅" if res['whatsapp'] or res['email'] else "⚠️"
                             log_container.write(f"{status_icon} {cli_nome}: Concluído.")
                         except Exception as e: log_container.error(f"❌ Erro em {cli_nome}: {e}")
                         if i < total_clientes - 1: time.sleep(10)
                     progresso.progress(100)
                     status_text.success("🏁 Finalizado!"); st.balloons(); time.sleep(3); st.rerun()
             st.divider()

        if not rel: 
            st.success("Nenhuma pendência encontrada.")
        else:
            for cli, info in rel.items():
                qtd = len(info['itens'])
                with st.expander(f"🔴 {cli} | R$ {info['total']:,.2f}"):
                    st.dataframe(pd.DataFrame(info['itens']), width="stretch")
                    c1, c2 = st.columns([1, 1])
                    key_zip = f"zip_{cli}"
                    with c1:
                        if st.button(f"🔍 Zipar {qtd}", key=f"bz_{cli}"):
                            with st.spinner("Processando..."):
                                path, temp_files = mgr.buscar_e_zipar_pdfs(cli, info['itens'])
                                if path: st.session_state[key_zip] = path; st.toast("ZIP Pronto!", icon="✅")
                        if st.session_state.get(key_zip) and os.path.exists(st.session_state[key_zip]):
                            with open(st.session_state[key_zip], "rb") as f: st.download_button("⬇️ Baixar", f, file_name=f"boletos_{cli}.zip", key=f"dl_{cli}")
                    with c2:
                        dados_do_cliente = info['dados_cliente'] 
                        msg_auto = mgr.gerar_mensagem_cobranca(cli, dados_do_cliente, info['total'], info['itens'])
                        msg = st.text_area("Texto", msg_auto, key=f"tx_{cli}", height=250)
                        zip_pronto = st.session_state.get(key_zip)
                        if st.button("📧 Enviar", key=f"s_{cli}", type="primary"):
                            mgr.executar_processo_completo_cobranca(cli, msg, zip_pronto, info['itens'])
                            st.success("Enviado!")

    # --- ABA 4: CRM & CARTEIRA ---
    with t4:
        st.subheader("👥 Gestão de Clientes e Carteira")
        
        # 1. BUSCA TOPO
        termo_busca = st.text_input("🔍 Buscar Cliente (Nome, CNPJ ou CPF)", placeholder="Digite e pressione Enter...")
        
        all_clis = listar_clientes_db(conf['empresa_cnpj'])
        df_clientes = pd.DataFrame(all_clis)
        
        if termo_busca and not df_clientes.empty:
            mask = df_clientes['nome'].str.contains(termo_busca, case=False, na=False) | \
                   df_clientes['cnpj'].str.contains(termo_busca, case=False, na=False)
            df_clientes = df_clientes[mask]
        
        if df_clientes.empty:
            st.info("Nenhum cliente encontrado com esses termos.")
        else:
            # 2. TABELA EDITÁVEL
            if "Selecionar" not in df_clientes.columns:
                df_clientes.insert(0, "Selecionar", False)
                
            st.caption("Edite os dados diretamente na tabela. Selecione a caixa lateral para ver Detalhes ou Excluir.")
            
            df_editado = st.data_editor(
                df_clientes[["Selecionar", "id", "nome", "cnpj", "whatsapp", "email"]],
                column_config={
                    "Selecionar": st.column_config.CheckboxColumn(required=True, width="small"),
                    "id": st.column_config.NumberColumn(disabled=True, width="small"),
                    "nome": st.column_config.TextColumn("Cliente / Razão Social"),
                    "cnpj": st.column_config.TextColumn("CNPJ/CPF"),
                    "whatsapp": st.column_config.TextColumn("WhatsApp"),
                    "email": st.column_config.TextColumn("E-mail"),
                },
                hide_index=True,
                width="stretch",
                key="editor_crm"
            )
            
            if st.button("💾 Salvar Alterações na Tabela"):
                for index, row in df_editado.iterrows():
                    mgr.cadastrar_cliente_completo(row['nome'], row['cnpj'], row['whatsapp'], row['email'], "")
                st.success("Dados atualizados!")
                time.sleep(1); st.rerun()

            selecionados = df_editado[df_editado['Selecionar'] == True]
            qtd_sel = len(selecionados)
            
            if qtd_sel > 0:
                st.divider()
                st.markdown(f"### ⚠️ Ações para {qtd_sel} selecionado(s)")
                
                col_del_1, col_del_2 = st.columns([1, 4])
                if col_del_1.button("🗑️ Excluir Selecionados", type="primary"):
                    st.session_state.confirmando_exclusao = True
                
                if st.session_state.get('confirmando_exclusao'):
                    st.warning(f"Tem certeza que deseja excluir {qtd_sel} clientes? Isso apagará todos os títulos e histórico deles.")
                    c_sim, c_nao = st.columns(2)
                    if c_sim.button("✅ SIM, Excluir Definitivamente"):
                        for _, row in selecionados.iterrows():
                            excluir_cliente_db(row['id'], row['nome'])
                        st.session_state.confirmando_exclusao = False
                        st.success("Excluídos com sucesso!")
                        time.sleep(1); st.rerun()
                    if c_nao.button("❌ Não, Cancelar"):
                        st.session_state.confirmando_exclusao = False
                        st.rerun()

            if qtd_sel == 1:
                cliente_foco = selecionados.iloc[0]
                st.divider()
                st.markdown(f"## 👤 Perfil: {cliente_foco['nome']}")
                
                tab_titulos, tab_hist = st.tabs(["💰 Títulos & Carteira", "📜 Histórico de Envios"])
                
                # A. Títulos
                with tab_titulos:
                    titulos = listar_titulos_por_cliente(cliente_foco['nome'], conf['empresa_cnpj'])
                    if not titulos:
                        st.info("Nenhum título cadastrado para este cliente.")
                    else:
                        df_t = pd.DataFrame(titulos)
                        df_t.insert(0, "Sel", False)
                        
                        df_tit_edit = st.data_editor(
                            df_t[['Sel', 'id', 'numero_nf', 'vencimento', 'valor', 'status', 'acao']],
                            column_config={
                                "Sel": st.column_config.CheckboxColumn(width="small"),
                                "id": st.column_config.NumberColumn(disabled=True, width="small"),
                                "status": st.column_config.SelectboxColumn("Status", options=["Aberto", "Pago", "Acordo", "Cancelado"], required=True),
                                "acao": st.column_config.SelectboxColumn("Ação", options=["Cobrar", "Aguardar", "Jurídico", "Cartório", "Pago"], required=True)
                            },
                            hide_index=True,
                            key="editor_titulos_single"
                        )
                        
                        if st.button("Salvar Alterações nos Títulos"):
                            mgr.salvar_edicao_titulos(df_tit_edit.drop(columns=['Sel']))
                            st.rerun()

                # B. Histórico
                with tab_hist:
                    st.markdown("##### 📅 Filtro de Data")
                    d1, d2, btn_filt, btn_pdf = st.columns([2, 2, 1, 2])
                    
                    if 'filtro_hist_ini' not in st.session_state: st.session_state.filtro_hist_ini = datetime.date.today() - datetime.timedelta(days=30)
                    if 'filtro_hist_fim' not in st.session_state: st.session_state.filtro_hist_fim = datetime.date.today()
                    
                    data_ini = d1.date_input("Início", value=st.session_state.filtro_hist_ini)
                    data_fim = d2.date_input("Fim", value=st.session_state.filtro_hist_fim)
                    
                    filtrar_agora = btn_filt.button("🔍 Filtrar", width="stretch")
                    
                    hist = mgr.buscar_historico_detalhado(cliente_foco['nome'])
                    
                    if not hist:
                        st.info("Nenhum registro de envio.")
                    else:
                        df_hist = pd.DataFrame(hist)
                        
                        if filtrar_agora:
                            st.session_state.filtro_hist_ini = data_ini
                            st.session_state.filtro_hist_fim = data_fim
                        
                        df_hist['Data_ISO'] = pd.to_datetime(df_hist['Data_ISO'], errors='coerce')
                        df_hist = df_hist.dropna(subset=['Data_ISO'])
                        
                        ts_ini = pd.to_datetime(st.session_state.filtro_hist_ini)
                        ts_fim = pd.to_datetime(st.session_state.filtro_hist_fim)
                        
                        df_hist_fil = df_hist[
                            (df_hist['Data_ISO'].dt.normalize() >= ts_ini) & 
                            (df_hist['Data_ISO'].dt.normalize() <= ts_fim)
                        ]
                        
                        st.dataframe(
                            df_hist_fil.drop(columns=['Data_ISO']), 
                            width="stretch", 
                            hide_index=True,
                            column_config={
                                "Títulos (NF)": st.column_config.TextColumn("Títulos (NF)", width="large"),
                                "Canais": st.column_config.TextColumn("Canais", width="medium"),
                            }
                        )
                        
                        if btn_pdf.button("🖨️ Gerar PDF", width="stretch"):
                            path_pdf = mgr.gerar_relatorio_historico_pdf(cliente_foco['nome'], df_hist_fil.to_dict('records'))
                            with open(path_pdf, "rb") as f:
                                st.download_button("⬇️ Baixar Relatório", f, file_name=os.path.basename(path_pdf), mime="application/pdf")

        # 5. NOVO CADASTRO
        st.divider()
        with st.expander("➕ Cadastrar Novo Cliente Manualmente"):
            with st.form("new_cli_man_crm"):
                cn1, cn2, cn3, cn4, cn5 = st.columns(5)
                n = cn1.text_input("Nome"); cp = cn2.text_input("CNPJ"); wa = cn3.text_input("Zap"); em = cn4.text_input("Email"); ct = cn5.text_input("Contato")
                if st.form_submit_button("Cadastrar"):
                    mgr.cadastrar_cliente_completo(n, cp, wa, em, ct)
                    st.success("Cadastrado!")
                    time.sleep(1); st.rerun()

    with t5: st.info("Relatórios gráficos em breve.")

# ==============================================================================
# GESTÃO & CONFIG
# ==============================================================================
elif selected == "Gestão":
    st.subheader("🏢 Unidades")
    unidades = carregar_todas_unidades_db()
    cols = st.columns(3)
    for i, u in enumerate(unidades):
        with cols[i % 3]:
            with st.container(border=True):
                st.markdown(f"**{u['empresa_nome']}**")
                if str(u.get('id')) == str(conf.get('id')): 
                    st.button("✅ Ativa", key=f"k_{u['id']}", disabled=True, width="stretch")
                else: 
                    st.button("Acessar", key=f"go_{u['id']}", on_click=ativar_empresa, args=(u,), width="stretch")
    if st.button("➕ Nova Filial"): st.session_state.novo_cadastro = True; st.session_state.config = {}; st.rerun()

elif selected == "Configurações":
    ct1, ct2, ct3, ct4, ct5 = st.tabs(["🔐 Senha", "👥 Usuários", "🟢 WhatsApp", "🕵️ E-mail", "⏰ Robô"])
    
    with ct1:
        st.write(f"Usuário: **{st.session_state.usuario_atual}**")
        with st.form("p"):
            s = st.text_input("Nova Senha", type="password")
            if st.form_submit_button("Alterar"): alterar_senha_usuario(st.session_state.usuario_atual, s); st.success("OK!")
    with ct2:
        with st.form("new_user"):
            c1, c2 = st.columns(2)
            u = c1.text_input("Login"); p = c2.text_input("Senha", type="password")
            if st.form_submit_button("Criar"):
                ok, msg = criar_usuario(u, p)
                if ok: st.success(msg)
                else: st.error(msg)
    with ct3:
        st.markdown("### 🟢 Configuração WhatsApp")
        def_url = os.getenv("EVO_API_URL") or conf.get('evo_url') or ""
        def_key = os.getenv("EVO_GLOBAL_KEY") or conf.get('evo_key') or ""
        with st.expander("🛠️ Editar API"):
            with st.form("fix_apis"):
                new_url = st.text_input("URL Evolution", value=def_url)
                new_key = st.text_input("Global Key", value=def_key, type="password")
                if st.form_submit_button("Salvar"):
                    st.session_state.config.update({"evo_url": new_url, "evo_key": new_key})
                    salvar_configuracoes_db(st.session_state.config); st.rerun()
        evo = EvolutionController(st.session_state.config)
        status = evo.checar_status()
        if status and 'instance' in status:
            st.success(f"Status: {status.get('instance', {}).get('state')}")
            if st.button("Resetar"): evo.deletar_instancia(); st.rerun()
        else:
            if st.button("Criar Instância"):
                res = evo.criar_instancia()
                if res and 'qrcode' in res: st.image(res['qrcode']['base64'], width=250)
    with ct4:
        st.markdown("### 🕵️ SMTP (Envio)")
        with st.form("form_smtp"):
            srv = st.text_input("Servidor SMTP", value=conf.get('smtp_server',''))
            usr = st.text_input("Usuário", value=conf.get('mail_user',''))
            pwd = st.text_input("Senha", value=conf.get('mail_pass',''), type="password")
            if st.form_submit_button("Salvar"):
                st.session_state.config.update({"smtp_server": srv, "mail_user": usr, "mail_pass": pwd})
                salvar_configuracoes_db(st.session_state.config); st.success("Salvo!")
    with ct5:
        st.markdown("### 🤖 Automação de Cobrança")
        ag = mgr.obter_agendamento()
        p_dias = ag.get('dias_ui', ["Segunda", "Sexta"]) if ag else ["Segunda", "Sexta"]
        p_hora = datetime.time(9,0)
        p_fer = ag.get('pular_feriados', True) if ag else True
        p_on = ag.get('ativo', False) if ag else False
        if ag and 'horario_envio' in ag:
            try: h,m = ag['horario_envio'].split(':'); p_hora = datetime.time(int(h), int(m))
            except: pass
        with st.form("form_robo"):
            c_on = st.toggle("Ativar Cobrança Automática", value=p_on)
            st.divider()
            dias_sel = st.multiselect("Dias:", ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"], default=p_dias)
            c1, c2 = st.columns(2)
            hora_sel = c1.time_input("Horário", value=p_hora)
            pular_fer = c2.checkbox("Pular Feriados", value=p_fer)
            if st.form_submit_button("💾 Salvar Programação"):
                mgr.salvar_config_agendamento(dias_sel, hora_sel.strftime("%H:%M"), pular_fer, c_on)
                st.success("Salvo!"); time.sleep(1); st.rerun()

# --- WIZARD NOVO CADASTRO ---
if st.session_state.get('novo_cadastro', False):
    st.markdown("---"); st.markdown("## 🧙‍♂️ Novo Cadastro")
    with st.form("wiz"):
        n = st.text_input("Nome Fantasia"); c = st.text_input("CNPJ")
        if st.form_submit_button("Salvar"):
            st.session_state.config.update({"empresa_nome": n, "empresa_cnpj": c})
            salvar_configuracoes_db(st.session_state.config)
            st.session_state.novo_cadastro = False; st.rerun()
    if st.button("Cancelar"): st.session_state.novo_cadastro = False; st.rerun()