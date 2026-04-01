# Credos - Sistema Autonomo de Gestao de Cobranca e Negociacao

**Versao:** 2.0 | **Idioma / Language:** Portugues-BR e English

---

## Portugues-BR

### Descricao Geral

O Credos e um sistema completo de gestao de cobrancas desenvolvido para empresas do segmento B2B. Ele automatiza todo o ciclo de vida de um titulo em atraso: desde o envio da primeira mensagem de cobranca via WhatsApp, passando pela negociacao autonoma com inteligencia artificial, ate o protocolo formal de protesto em cartorio.

O sistema e projetado para funcionar 24 horas por dia, 7 dias por semana, sem intervencao humana na maior parte do fluxo. O operador so e acionado em pontos criticos de decisao, como aprovacao de acordos, analise de comprovantes de pagamento e autorizacao de protestos.

---

### Funcionalidades

#### Gestao de Titulos (CRM)
- Cadastro de clientes com CNPJ, telefone, e-mail e endereco completo.
- Importacao de titulos e notas fiscais com valor, vencimento e numero do documento.
- Visualizacao separada por abas: Inadimplentes, Pagos e Historico, e Cartorio.
- Atualizacao manual e automatica de status: Aberto, Pago, Negociado, Cartorio, Baixado.
- Selecao multipla de titulos para acoes em lote (marcar como pago ou enviar ao cartorio).
- Controle individual de fluxo por titulo (Cobrar ou Pausar).

#### Cobranca Automatica via WhatsApp
- Disparo automatico de mensagens de cobranca conforme agenda configurada (dia da semana e horario).
- Geracao de mensagem personalizada com inteligencia artificial (Google Gemini), incluindo nome do cliente, valor total e lista de notas fiscais.
- Busca e anexo automatico dos PDFs das notas fiscais a partir da caixa de e-mail da empresa, compactados em ZIP.
- Mecanismo de seguranca tripla: o sistema verifica o status do titulo no banco de dados imediatamente antes de cada disparo, impedindo que clientes com titulos ja quitados recebam cobrancas indevidas.
- Suporte a multiplos numeros de WhatsApp por cliente (separados por ponto e virgula).

#### Negociacao Autonoma com Inteligencia Artificial (Analu)
- Apos o envio da primeira mensagem, a IA assume a negociacao automaticamente com o cliente.
- A IA mantém historico de conversa (ultimas 20 mensagens para contexto da IA, 100% do historico para fins juridicos).
- Classificacao automatica de intencao do cliente: pagamento imediato, pedido de prazo, comprovante enviado, solicitacao de suporte, negativacao ou encerramento.
- Deteccao de multiplas mensagens progressivas do cliente (o sistema aguarda o cliente terminar de escrever antes de responder).
- Gerecao de propostas de acordo com data de pagamento e confirmacao via WhatsApp do operador.
- Ciclo de negociacao de 20 dias: a cada dia, a IA envia uma mensagem com tom progressivamente mais firme.
- Ao atingir o Dia 20 sem pagamento, o operador recebe um alerta automatico no WhatsApp perguntando se deve enviar os titulos ao cartorio.

#### Protocolo de Protesto em Cartorio
- Automacao completa do fluxo de protesto no portal pesquisaprotesto.com.br via Playwright (browser automation).
- O robo herda a sessao do navegador do operador (login e certificado digital ja autenticados), eliminando a necessidade de reautenticacao.
- Preenchimento automatico de todos os 5 passos do assistente de protesto:
  - Passo 1: Dados da Divida (Especie DM, numero da NF, datas de emissao e vencimento, valores).
  - Passo 2: Dados do Credor (preenchidos automaticamente a partir das configuracoes da empresa).
  - Passo 3: Dados do Devedor (CNPJ, nome, e-mail, telefone e endereco completo do cliente).
  - Passo 4: Revisao final.
  - Passo 5: Clique no botao "Solicitar o Protesto" (com screenshot de confirmacao salvo).
- Fila de protesto com controle de intervalo minimo entre envios.
- Extracao automatica da data de emissao da nota fiscal a partir do e-mail da empresa, caso nao esteja preenchida no banco.

#### Acompanhamento Pos-Protesto
- Apos o envio ao cartorio, o sistema registra data e hora do protocolo.
- Apos 5 dias sem confirmacao de retorno, o sistema notifica o operador via WhatsApp com tres opcoes de acao:
  - Confirmar que o cartorio acatou o titulo.
  - Solicitar reenvio com dados corrigidos (o titulo volta automaticamente para a fila de automacao).
  - Cancelar o protesto e reabrir o titulo na cobranca normal.
- O operador responde via WhatsApp com comandos simples (ex: CARTORIO_ACATOU, CARTORIO_REENVIAR, CARTORIO_CANCELAR).

#### Historico de Conversas (Compliance Juridico)
- Armazenamento de 100% das mensagens trocadas via WhatsApp entre o sistema e cada cliente.
- Cada mensagem e gravada com timestamp preciso, permitindo rastreabilidade completa.
- Filtro de periodo (data inicial e data final) para consulta.
- Impressao e exportacao em PDF do historico, formatada em modo retrato para economia de papel.
- Dados validos para uso como prova em disputas juridicas ou negociacoes formais.

#### Gestao de Comprovantes de Pagamento
- Clientes podem enviar fotos ou arquivos de comprovantes diretamente pelo WhatsApp.
- O sistema armazena o comprovante e notifica o operador para analise.
- O operador pode aprovar ou recusar o comprovante via dashboard web.
- Aprovacao automaticamente altera o status do titulo para Pago e encerra o ciclo de cobranca.

#### Painel Administrativo Web
- Interface web moderna e responsiva construida em React com Vite.
- Suporte a modo escuro e modo claro.
- Dashboard com resumo financeiro e ultimas atividades.
- Modulo de configuracoes da empresa: dados do credor, credenciais de e-mail, chave PIX, horario de cobranca, dias da semana e numero do operador.
- Modulo de agendamentos com controle fino de automacao.
- Modulo de relatorios financeiros exportaveis.
- Acesso protegido por autenticacao (usuario e senha com hash seguro).

#### Backup Automatico
- Backup diario automatico do banco de dados SQLite para o Google Drive (pasta MeuDrive/Credos/Backup).
- Execucao agendada as 12:00 todos os dias pelo scheduler interno.
- Log de sucesso e falha registrado em arquivo robot.log.

---

### Tecnologias Utilizadas

**Backend**
- Python 3.13
- FastAPI - framework de API REST de alta performance
- SQLite - banco de dados leve e portavel por empresa (multi-tenant)
- Playwright - automacao de browser para o portal do cartorio
- Google Gemini API - modelo de linguagem para geracao de mensagens e negociacao IA
- Evolution API - gateway de WhatsApp para envio e recebimento de mensagens
- IMAP / smtplib - integracao com caixas de e-mail para busca de notas fiscais
- Google Drive API - backup automatico de dados
- Schedule - agendamento de tarefas em background
- Uvicorn - servidor ASGI de producao

**Frontend**
- React 18 com TypeScript
- Vite - bundler e servidor de desenvolvimento
- Tailwind CSS - framework de estilos utilitarios
- Axios - cliente HTTP para comunicacao com a API
- Lucide React - biblioteca de icones
- CSS puro com media queries de impressao (@media print)

**Infraestrutura**
- Docker e Docker Compose - containerizacao para deploy em nuvem
- Oracle Cloud Infrastructure (OCI) - hospedagem em producao
- GitHub - versionamento de codigo

---

---

## English

### Overview

Credos is a complete debt collection management system built for B2B companies. It automates the entire lifecycle of an overdue invoice: from sending the first collection message via WhatsApp, through autonomous AI-powered negotiation, to the formal protest process at the notary office (cartorio).

The system is designed to run 24/7 with minimal human intervention. The operator is only involved at critical decision points, such as approving payment agreements, reviewing payment receipts, and authorizing formal protests.

---

### Features

#### Title and Invoice Management (CRM)
- Customer registration with tax ID (CNPJ), phone, email, and full address.
- Invoice import with amount, due date, and document number.
- Separate tab views: Overdue, Paid and History, and Notary Office.
- Manual and automatic status updates: Open, Paid, Negotiated, Notary, Archived.
- Bulk title selection for batch actions (mark as paid or send to notary).
- Individual flow control per title (Collect or Pause).

#### Automated WhatsApp Collection
- Automatic collection messages dispatched on a configurable schedule (day of week and time).
- AI-generated personalized messages (Google Gemini), including customer name, total amount, and invoice list.
- Automatic retrieval and attachment of invoice PDFs from the company email inbox, compressed as ZIP.
- Triple-safety mechanism: the system re-validates the invoice status in the database immediately before each dispatch, preventing customers with settled invoices from receiving erroneous charges.
- Support for multiple WhatsApp numbers per customer (semicolon-separated).

#### Autonomous AI Negotiation (Analu)
- After the first message is sent, the AI autonomously handles negotiation with the customer.
- The AI maintains conversation history (last 20 messages for AI context, 100% history for legal compliance).
- Automatic customer intent classification: immediate payment, payment extension request, receipt submitted, support request, credit reporting threat, or conversation close.
- Detection of progressive multi-message inputs (the system waits for the customer to finish typing before responding).
- Generation of payment agreement proposals with a confirmed payment date, approved via operator WhatsApp.
- 20-day negotiation cycle: each day the AI sends a message with a progressively firmer tone.
- On Day 20 without payment, the operator receives an automatic WhatsApp alert asking whether to escalate to the notary office.

#### Notary Protest Automation
- Full automation of the protest flow on the pesquisaprotesto.com.br portal using Playwright (browser automation).
- The robot inherits the operator's live browser session (login and digital certificate already authenticated), eliminating the need for re-authentication.
- Automatic completion of all 5 steps of the protest wizard:
  - Step 1: Debt Details (Species DM, invoice number, emission and due dates, amounts).
  - Step 2: Creditor Details (auto-filled from company settings).
  - Step 3: Debtor Details (tax ID, name, email, phone, and full address).
  - Step 4: Review.
  - Step 5: Click "Request Protest" button (with a confirmation screenshot saved).
- Protest queue with configurable minimum interval between submissions.
- Automatic extraction of the invoice emission date from the company email inbox if not already in the database.

#### Post-Protest Tracking
- After submission to the notary, the system records the date and time of the protocol.
- After 5 days without a confirmed response, the system notifies the operator via WhatsApp with three action options:
  - Confirm that the notary accepted the title.
  - Request resubmission with corrected data (the title is automatically re-queued for automation).
  - Cancel the protest and reopen the title for normal collection.
- The operator responds via WhatsApp with simple commands (e.g., CARTORIO_ACATOU, CARTORIO_REENVIAR, CARTORIO_CANCELAR).

#### Conversation History (Legal Compliance)
- Full 100% storage of all WhatsApp messages exchanged between the system and each customer.
- Each message is recorded with a precise timestamp, enabling complete traceability.
- Date range filter (start date and end date) for queries.
- Print and PDF export of conversation history, formatted in portrait mode for paper efficiency.
- Data is legally valid for use as evidence in disputes or formal negotiations.

#### Payment Receipt Management
- Customers can send photos or files of payment receipts directly via WhatsApp.
- The system stores the receipt and notifies the operator for review.
- The operator can approve or reject the receipt via the web dashboard.
- Approval automatically updates the invoice status to Paid and closes the collection cycle.

#### Web Admin Panel
- Modern, responsive web interface built with React and Vite.
- Dark mode and light mode support.
- Dashboard with financial summary and recent activity.
- Company settings module: creditor details, email credentials, PIX key, collection schedule, weekdays, and operator phone number.
- Scheduling module with fine-grained automation control.
- Exportable financial reports.
- Access protected by authentication (username and password with secure hashing).

#### Automatic Backup
- Daily automatic backup of the SQLite database to Google Drive (folder: MeuDrive/Credos/Backup).
- Scheduled at 12:00 (noon) every day by the internal scheduler.
- Success and failure logs recorded in robot.log.

---

### Technologies Used

**Backend**
- Python 3.13
- FastAPI - high-performance REST API framework
- SQLite - lightweight, portable per-company database (multi-tenant)
- Playwright - browser automation for the notary portal
- Google Gemini API - language model for message generation and AI negotiation
- Evolution API - WhatsApp gateway for sending and receiving messages
- IMAP / smtplib - email inbox integration for invoice retrieval
- Google Drive API - automated data backup
- Schedule - background task scheduling
- Uvicorn - production ASGI server

**Frontend**
- React 18 with TypeScript
- Vite - bundler and development server
- Tailwind CSS - utility-first styling framework
- Axios - HTTP client for API communication
- Lucide React - icon library
- Vanilla CSS with print media queries (@media print)

**Infrastructure**
- Docker and Docker Compose - containerization for cloud deployment
- Oracle Cloud Infrastructure (OCI) - production hosting
- GitHub - source code versioning

---

### Setup and Running

```bash
# Backend
pip install -r requirements.txt
uvicorn api.main:app --host 0.0.0.0 --port 8001 --reload

# Frontend
cd frontend
npm install
npm run dev

# Background Scheduler (collection robot)
python robot_scheduler.py
```

---

### License

Proprietary software. All rights reserved. Unauthorized copying, distribution, or modification is strictly prohibited.

(c) 2025-2026 Credos. All rights reserved.
