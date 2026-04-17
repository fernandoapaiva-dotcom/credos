# Credos System 🚀 / 🇬🇧 English Below

**Credos System** é uma plataforma SaaS multi-tenant avançada para automação de cobranças, negociação inteligente de dívidas e gestão financeira via WhatsApp, e-mail e Cartórios. Alimentado por Inteligência Artificial (Google Gemini), o sistema atua como um assistente financeiro predatório e amigável (Analu) que orquestra autonomamente todo o fluxo de ponta a ponta.

## 🛠️ Tecnologias Utilizadas

### Backend & Core
*   **Python 3.12+** / **FastAPI**: Backend robusto e assíncrono.
*   **SQLite Multi-Tenant**: Bancos isolados dinamicamente por CNPJ (LGPD Safe).
*   **Google Gemini AI (Flash/Pro)**: Motor de NLP para a Analu (Agente Conversacional com Function Calling e RAG).
*   **Evolution API (v1.8.7)**: Motor de disparo e recebimento no WhatsApp (Multi-device).
*   **Pandas & FPDF2**: Processamento de dados e geração de Relatórios Executivos em PDF Diários.
*   **IMAP/SMTP Libs (MailScanner)**: Leitura autônoma de e-mails para ingestão de Notas Fiscais (NFe/NFSe) e Boletos.
*   **OpenSSL / PKCS12**: Suporte a certificado digital (.pfx) para automação de cartórios.

### Frontend & Infraestrutura
*   **React + TailwindCSS**: Dashboard responsivo para os supervisores (vite).
*   **Docker & Docker Compose**: Orquestração conteinerizada de todos os micro-serviços (Front, Back e Evolution API).
*   **Nginx**: Proxy reverso de frontend.
*   **Oracle Cloud Infrastructure (OCI)**: Nuvem de hospedagem.

---

## ⚙️ Funcionalidades Principais 

### 🤖 Analu Agentic AI (Assistente Financeira Inteligente)
*   **Memória de Grupo e Contexto**: Mantém o contexto nas conversas, sabe se apresentar em nome de dezenas de empresas diferentes.
*   **Execução de Ações por Chat**: Supervisores podem mandar ações via WhatsApp: *"Analu, cobre o cliente da Empresa X"*. Ela busca a dívida e executa a régua de cobrança.
*   **RAG Negotiator**: Negocia abatimentos e descontos de forma humanizada usando o limite imposto pela administração do sistema, via DM com o cliente final.

### 💸 Régua de Cobrança Autônoma
*   **Agendamento Cron (Worker)**: Robô diário que roda (ex: às 09:00), lendo clientes vencidos e enviando mensagens automáticas de cobrança.
*   **Motor de Juros e Multas em Tempo Real**: Calcula multa fixa e juros proporcionais aos dias de atraso a cada disparo.
*   **Processamento de Múltiplos Canais**: Envio de comprovantes por WhatsApp e Email simultaneamente.

### 📨 MailScanner (Ingestão Automática de Títulos)
*   Lê caixas de e-mail específicas à procura de novos Boletos e arquivos `.xml/.pdf` de Notas Fiscais.
*   "Regra de Ouro": Associa e soma valores de boletos a NF-e e NFS-e, injetando as dívidas diretamente no sistema.

### 🏛️ Automação de Cartório/Protesto
*   Rastreia títulos que cruzaram o limite de dias em atraso (ex: 10 dias).
*   Cria PDFs legais automáticos e encaminha via integração de notificação judicial (com certificado digital).

### 📊 Relatórios Premium
*   Gera relatórios diários de performance automaticamente ("Acionamentos vs. Entregas").
*   Dispara o arquivo executivo para o grupo de supervisão em formato PDF todas as manhãs.

---

---

# Credos System 🚀 (English)

**Credos System** is an advanced multi-tenant SaaS platform for automated debt collection, intelligent negotiation, and financial management via WhatsApp, email, and Notary Offices. Powered by Artificial Intelligence (Google Gemini), the system acts as a smart financial assistant (Analu) that autonomously orchestrates the end-to-end billing workflow.

## 🛠️ Tech Stack

### Backend & Core
*   **Python 3.12+** / **FastAPI**: Robust, asynchronous backend.
*   **Multi-Tenant SQLite**: Dynamically isolated databases per company CNPJ (GDPR Safe).
*   **Google Gemini AI (Flash/Pro)**: NLP engine for Analu (Conversational Agent with Function Calling and RAG).
*   **Evolution API (v1.8.7)**: WhatsApp sending and receiving engine (Multi-device).
*   **Pandas & FPDF2**: Data processing and Daily PDF Executive Report generation.
*   **IMAP/SMTP Libs (MailScanner)**: Autonomous email reading to ingest Invoices (XML/PDF) and Bank Slips.
*   **OpenSSL / PKCS12**: Digital certificate (.pfx) support for notary automation.

### Frontend & Infrastructure
*   **React + TailwindCSS**: Responsive dashboard for supervisors (Vite).
*   **Docker & Docker Compose**: Containerized orchestration of all micro-services (Front, Back, and Evolution API).
*   **Nginx**: Frontend reverse proxy.
*   **Oracle Cloud Infrastructure (OCI)**: Hosting environment.

---

## ⚙️ Core Features

### 🤖 Analu Agentic AI (Smart Financial Assistant)
*   **Group Memory & Context**: Maintains context in conversations and intelligently represents dozens of different companies.
*   **Action Execution via Chat**: Supervisors can issue commands via WhatsApp: *"Analu, charge the client from Company X"*. She fetches the debt and runs the billing protocol.
*   **RAG Negotiator**: Humanized negotiation for discounts and debt settlement using limits set by system administrators, acting directly in the client's DMs.

### 💸 Autonomous Billing Protocol
*   **Cron Scheduler (Worker)**: Daily robot that runs (e.g., at 09:00 AM), reading overdue clients and sending automated billing messages.
*   **Real-time Interest & Fines Engine**: Calculates fixed fines and proportional interest for late days on every dispatch.
*   **Omnichannel Processing**: Sends payment proofs via WhatsApp and Email simultaneously.

### 📨 MailScanner (Automatic Debt Ingestion)
*   Scans specific email inboxes looking for new Bills and Invoice `.xml/.pdf` files.
*   "Golden Rule": Groups and sums the values of bank slips to product and service invoices, injecting the debts directly into the system.

### 🏛️ Notary/Protest Automation
*   Tracks debts that cross the maximum overdue limit (e.g., 10 days).
*   Automatically creates legal PDF notifications and forwards them via judicial notification gateways (using digital certificates).

### 📊 Premium Reports
*   Generates daily performance reports ("Triggers vs. Deliveries" & efficiency rates).
*   Automatically broadcasts the executive summary file (PDF) to the WhatsApp supervisor group every morning.
