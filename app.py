import streamlit as st
import os
import pandas as pd
import requests
import time
from dotenv import load_dotenv

# Importações do ecossistema src/
from src.extractor import extrair_dados_boletos
from src.database import (
    salvar_dados_no_banco, inicializar_banco, get_connection, 
    obter_metricas_mensais
)
from src.manager import Manager
from src.ai_handler import get_ai_response

# Carregar variáveis de ambiente
load_dotenv()

# Configuração da Página
st.set_page_config(page_title="Credos SaaS", page_icon="🛡️", layout="wide")

# Inicializar Banco de Dados
inicializar_banco()

# --- ESTILIZAÇÃO CUSTOMIZADA ---
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stButton>button { width: 100%; border-radius: 8px; font-weight: bold; }
    .stExpander { background-color: white; border-radius: 10px; border: 1px solid #ddd; }
    .css-1kyx06p { background-color: #f1f3f6; } /* Cor de fundo das tabs */
    </style>
    """, unsafe_allow_html=True)

st.title("🛡️ Credos: Recuperação de Crédito Inteligente")

# --- SIDEBAR: CONTROLE E IMPORTAÇÃO ---
with st.sidebar:
    st.header("⚙️ Painel de Controle")
    empresa = st.selectbox("Selecione a Credora:", ["SERVWELD", "Centro-Oeste"])
    cnpj_credor = "11504286000169" if empresa == "SERVWELD" else "54804458000122"
    
    st.markdown("---")
    st.subheader("📥 Importar Dados")
    uploaded_file = st.file_uploader("Upload de PDF Itaú (Vencidos)", type="pdf")
    
    if uploaded_file and st.button("🚀 Processar e Sincronizar"):
        temp_path = os.path.join("data", f"{int(time.time())}_{uploaded_file.name}")
        if not os.path.exists("data"): os.makedirs("data")
            
        try:
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            with st.status("Processando PDF...", expanded=True) as status:
                st.write("🔍 Extraindo dados com IA...")
                dados = extrair_dados_boletos(temp_path, cnpj_credor)
                
                if dados:
                    st.write("💾 Sincronizando com Banco de Dados...")
                    mgr_sidebar = Manager(cnpj_credor)
                    mgr_sidebar.conciliar_titulos(dados)
                    salvar_dados_no_banco(dados, cnpj_credor)
                    status.update(label="✅ Sincronização concluída!", state="complete", expanded=False)
                    st.success(f"{len(dados)} títulos importados.")
                    time.sleep(1.5)
                    st.rerun()
        except Exception as e:
            st.error(f"❌ Erro: {e}")

# --- CORPO PRINCIPAL: ABAS ---
mgr = Manager(cnpj_credor)
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 Cobrança", "⚠️ Conciliação", "🤝 Promessas", "📈 Dashboard", "👥 Clientes", "📲 Conexão"
])

# ABA 1: GESTÃO DE COBRANÇA
with tab1:
    st.subheader(f"Títulos em Aberto: {empresa}")
    relatorio = mgr.agrupar_debitos_por_cliente()
    
    if not relatorio:
        st.info("Nenhum título vencido encontrado.")
    else:
        for cliente, info in relatorio.items():
            # Filtro para remover duplicatas visualmente (NF 101, NF 101 -> NF 101)
            notas_unicas = sorted(list(set(info['itens'])))
            exp_label = f"📌 {cliente} | Dívida Total: R$ {info['total']:,.2f}"
            
            with st.expander(exp_label):
                if info['contato']: st.caption(f"👤 Responsável: {info['contato']} | 📱 {info['zap']}")
                st.write(f"**Pendências:** {', '.join(notas_unicas)}")
                
                c1, c2, c3 = st.columns(3)
                
                # Botão 1: WhatsApp Padrão
                if c1.button(f"📲 WhatsApp Rápido", key=f"zap_{cliente}"):
                    msg = mgr.messenger.formatar_mensagem_cobranca(cliente, info)
                    sucesso, status_msg = mgr.messenger.enviar_whatsapp(info['zap'], msg)
                    st.toast(status_msg)

                # Botão 2: E-mail (HTML)
                if c2.button(f"📧 E-mail Profissional", key=f"mail_{cliente}"):
                    with st.spinner("Enviando e-mail..."):
                        sucesso, status_msg = mgr.mailer.enviar_email_cobranca(info['email'], cliente, info)
                        st.toast(status_msg)

                # Botão 3: Sugerir Acordo com Gemini (Prompt Robusto)
                if c3.button(f"🤖 Acordo IA", key=f"ai_{cliente}"):
                    with st.spinner("Gemini elaborando proposta personalizada..."):
                        # Prompt focado em negociação real
                        query = (
                            f"Atue como um gestor de cobrança amigável da empresa {empresa}. "
                            f"O cliente {cliente} possui um débito total de R$ {info['total']:,.2f}. "
                            f"As notas fiscais são: {', '.join(notas_unicas)}. "
                            f"Escreva uma mensagem para WhatsApp curta e profissional. "
                            f"Inicie com uma saudação, mencione os valores e pergunte se "
                            f"podem enviar o comprovante ou se precisam de uma segunda via do boleto. "
                            f"Seja cordial, evite termos jurídicos pesados."
                        )
                        st.session_state[f"prop_{cliente}"] = get_ai_response(query)

                # Área de Revisão da IA (Só aparece se a IA for acionada)
                if f"prop_{cliente}" in st.session_state:
                    st.markdown("---")
                    st.info("💡 **Proposta sugerida pela IA (Você pode editar antes de enviar):**")
                    proposta_editavel = st.text_area(
                        "Mensagem da IA:", 
                        value=st.session_state[f"prop_{cliente}"],
                        height=180,
                        key=f"area_{cliente}"
                    )
                    
                    col_env, col_can = st.columns([2, 1])
                    if col_env.button("🚀 Disparar Proposta", key=f"send_ai_{cliente}", type="primary"):
                        sucesso, status_msg = mgr.messenger.enviar_whatsapp(info['zap'], proposta_editavel)
                        if sucesso:
                            st.success("Enviado com sucesso!")
                            del st.session_state[f"prop_{cliente}"]
                            st.rerun()
                        else:
                            st.error(status_msg)
                    
                    if col_can.button("Cancelar", key=f"cancel_{cliente}"):
                        del st.session_state[f"prop_{cliente}"]
                        st.rerun()

# ABA 6: CONEXÃO (EVOLUTION API)
with tab6:
    st.subheader("📲 Configuração do WhatsApp")
    url = os.getenv("SERVER_URL")
    key = os.getenv("AUTHENTICATION_API_KEY")
    inst = os.getenv("INSTANCE_NAME")

    st.write(f"Conectando em: `{url}` | Instância: `{inst}`")
    
    c1, c2 = st.columns(2)
    with c1:
        if st.button("📊 Verificar API"):
            try:
                res = requests.get(f"{url}/instance/fetchInstances", headers={"apikey": key}, timeout=5)
                if res.status_code == 200: st.success("🟢 Comunicação OK!")
                else: st.error(f"🔴 Erro {res.status_code}: Verifique a API Key.")
            except: st.error("🔴 Servidor Offline.")

    with c2:
        if st.button("🔄 Criar / Gerar QR Code"):
            headers = {"apikey": key, "Content-Type": "application/json"}
            requests.post(f"{url}/instance/create", json={"instanceName": inst, "qrcode": True}, headers=headers)
            res = requests.get(f"{url}/instance/connect/{inst}", headers=headers)
            if res.status_code == 200 and "base64" in res.json():
                st.image(res.json()["base64"], caption="Escaneie para conectar")
            else: st.info("Instância já ativa ou conectada.")