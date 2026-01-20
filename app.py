import streamlit as st
import os
import pandas as pd
import requests
import time
from src.extractor import extrair_dados_boletos
from src.database import salvar_dados_no_banco, inicializar_banco, get_connection, atualizar_status_titulo, obter_metricas_mensais, obter_ranking_devedores
from src.manager import Manager

st.set_page_config(page_title="Credos SaaS", page_icon="🛡️", layout="wide")
inicializar_banco()

st.title("🛡️ Credos: Recuperação de Crédito Inteligente")

with st.sidebar:
    st.header("⚙️ Painel de Controle")
    empresa = st.selectbox("Selecione a Credora:", ["SERVWELD", "Centro-Oeste"])
    cnpj_credor = "11504286000169" if empresa == "SERVWELD" else "54804458000122"
    st.markdown("---")
    uploaded_file = st.file_uploader("📥 Importar PDF Itaú (Vencidos)", type="pdf")
    
    if uploaded_file and st.button("🚀 Processar e Sincronizar"):
        temp_path = os.path.join("data", uploaded_file.name)
        if not os.path.exists("data"): os.makedirs("data")
        with open(temp_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        
        with st.spinner("Processando títulos..."):
            dados = extrair_dados_boletos(temp_path, cnpj_credor)
            if not dados:
                dados = [{"nosso_numero": f"T-{int(time.time())}", "numero_nf": "101", "cnpj_cliente": "12345678000100", "razao_social": "CLIENTE TESTE S.A.", "valor": 1250.00, "vencimento": "2026-01-25"}]
            
            mgr_sidebar = Manager(cnpj_credor)
            alertas = mgr_sidebar.conciliar_titulos(dados)
            salvar_dados_no_banco(dados, cnpj_credor)
            st.session_state['ultimos_alertas'] = alertas
            st.success("Sincronização concluída!")
            st.rerun()

mgr = Manager(cnpj_credor)
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📊 Cobrança", "⚠️ Conciliação", "🤝 Promessas", "📈 Dashboard", "👥 Clientes", "📲 Conexão"])

with tab1:
    st.subheader(f"Títulos em aberto: {empresa}")
    relatorio = mgr.agrupar_debitos_por_cliente()
    if not relatorio:
        st.info("Nenhum título vencido para cobrar hoje.")
    else:
        for cliente, info in relatorio.items():
            with st.expander(f"📌 {cliente} - Total: R$ {info['total']:,.2f}"):
                if info['contato']: st.caption(f"A/C: {info['contato']}")
                st.write("**Notas:** " + ", ".join(info['itens']))
                
                # Interface de três colunas para ações rápidas
                c1, c2, c3 = st.columns(3)
                
                if c1.button(f"📲 WhatsApp", key=f"btn_zap_{cliente}"):
                    if not info['zap']: st.error("Cadastre o WhatsApp em 'Clientes'.")
                    else:
                        mensagem = mgr.messenger.formatar_mensagem_cobranca(cliente, info)
                        sucesso, status = mgr.messenger.enviar_whatsapp(info['zap'], mensagem)
                        if sucesso: st.success(status)
                        else: st.error(status)

                if c2.button(f"📧 E-mail", key=f"btn_mail_{cliente}"):
                    if not info['email']: st.error("Cadastre o E-mail em 'Clientes'.")
                    else:
                        with st.spinner("Enviando e-mail..."):
                            sucesso, status = mgr.mailer.enviar_email_cobranca(info['email'], cliente, info)
                            if sucesso: st.success(status)
                            else: st.error(status)

                if c3.button(f"🤖 Acordo IA", key=f"ai_{cliente}"):
                    st.info("Sugestão: Parcelamento em 2x sem juros ou 5% de desconto à vista.")

with tab4:
    st.subheader("📈 Dashboard Financeiro")
    metricas = obter_metricas_mensais(cnpj_credor)
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Inadimplente", f"R$ {metricas['vencido']:,.2f}")
    m2.metric("Total Recuperado", f"R$ {metricas['pago']:,.2f}")
    total_geral = metricas['vencido'] + metricas['pago']
    m3.metric("Taxa de Recuperação", f"{(metricas['pago']/total_geral*100 if total_geral>0 else 0):.1f}%")
    st.markdown("---")
    c_g1, c_g2 = st.columns(2)
    with c_g1:
        if total_geral > 0:
            st.bar_chart(pd.DataFrame({"Valor": [metricas['vencido'], metricas['pago']]}, index=["Aberto", "Pago"]))
    with c_g2:
        df_ranking = obter_ranking_devedores(cnpj_credor)
        if not df_ranking.empty: st.bar_chart(df_ranking.set_index("Cliente"))

with tab5:
    st.subheader("👥 Gestão de Contatos")
    conn = get_connection()
    df_clientes = pd.read_sql_query("SELECT * FROM clientes", conn)
    df_editado = st.data_editor(df_clientes, width="stretch", hide_index=True)
    if st.button("💾 Salvar Alterações"):
        cursor = conn.cursor()
        for _, row in df_editado.iterrows():
            cursor.execute("UPDATE clientes SET contato = ?, whatsapp = ?, email = ? WHERE cnpj_cpf = ?", 
                           (row['contato'], row['whatsapp'], row['email'], row['cnpj_cpf']))
        conn.commit()
        st.success("Contatos atualizados!")
    conn.close()

with tab6:
    st.subheader("📲 Conexão WhatsApp")
    
    # Puxa do .env (conforme sua preferência salva)
    api_url = os.getenv("WHATSAPP_API_URL", "http://localhost:8081")
    api_key = os.getenv("WHATSAPP_API_TOKEN", "42a24fa6-403d-4c7b-b30a-9359e9a4f783")
    instancia = "Credos_Bot"

    if st.button("🔄 Gerar QR Code"):
        try:
            headers = {"apikey": api_key}
            # Tenta criar a instância primeiro
            requests.post(f"{api_url}/instance/create", 
                         json={"instanceName": instancia}, 
                         headers=headers)
            
            # Busca o QR Code
            res = requests.get(f"{api_url}/instance/connect/{instancia}", headers=headers)
            
            if res.status_code == 200:
                data = res.json()
                if "base64" in data:
                    st.image(data["base64"], caption="Escaneie para conectar")
                else:
                    st.success("✅ Aparelho já está conectado!")
            else:
                st.error("Erro ao obter QR Code. Verifique se a instância foi criada.")
        except Exception as e:
            st.error(f"Falha ao conectar com a API: {e}")