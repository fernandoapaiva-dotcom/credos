from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routers import auth, companies, crm, reports, import_pdf, users, negotiation, cartorio, webhook
from contextlib import asynccontextmanager
import asyncio
import schedule
from src.worker import disparar_cobranca_automatica, processar_fila_cartorio

async def run_schedule():
    while True:
        schedule.run_pending()
        await asyncio.sleep(60)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Roda o worker de cobrança e agendamentos a cada minuto
    schedule.every().minute.do(disparar_cobranca_automatica)
    schedule.every().minute.do(processar_fila_cartorio)
    task = asyncio.create_task(run_schedule())
    yield
    task.cancel()

app = FastAPI(title="Credos API", description="Backend for the Credos React Application", lifespan=lifespan)

# Configuração de CORS para permitir que o React converse com a API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Pode ser restrito em produção para a URL do React
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

# Adicionando os modulos
app.include_router(users.router, prefix="/api/users", tags=["Users Management"])
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(companies.router, prefix="/api/companies", tags=["Companies"])
app.include_router(crm.router, prefix="/api/crm", tags=["CRM & Titles"])
app.include_router(reports.router, prefix="/api/reports", tags=["Reports"])
app.include_router(import_pdf.router, prefix="/api/import", tags=["Import PDF"])
app.include_router(negotiation.router, prefix="/api/negotiation", tags=["AI Negotiation"])
app.include_router(cartorio.router, prefix="/api/cartorio", tags=["Cartorio Automation"])
app.include_router(webhook.router, prefix="/api/webhook", tags=["WhatsApp Webhook"])
app.include_router(webhook.router, prefix="/api/evolution", tags=["Legacy Webhook Router"])

@app.get("/")
def read_root():
    return {"message": "Bem-vindo a API do Credos SaaS"}
