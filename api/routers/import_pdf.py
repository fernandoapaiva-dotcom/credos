from fastapi import APIRouter, HTTPException, Header, UploadFile, File, Form
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from src.extractor import ler_pdf_bruto, processar_dataframe_mapeado
from src.database import listar_clientes_db, salvar_dados_no_banco, conectar
import tempfile
import pandas as pd
import tempfile
import pandas as pd
import json
from src.manager import Manager

router = APIRouter()

class LayoutData(BaseModel):
    id: Optional[int] = None
    nome_layout: str
    col_vencimento: str
    col_numero: str
    col_valor: str
    col_pagador: str

@router.post("/upload")
async def upload_pdf(
    x_company_cnpj: str = Header(...),
    layout: str = Form(...), # JSON string of LayoutData due to multipart/form-data
    file: UploadFile = File(...)
):
    try:
        layout_dict = json.loads(layout)
        
        # Salva em um arquivo temporario
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name
        
        # Usa o extractor existente
        df_bruto = ler_pdf_bruto(tmp_path)
        if df_bruto is None:
            raise HTTPException(status_code=400, detail="Não foi possível ler o PDF")
            
        mapa_atual = {
            'vencimento': layout_dict['col_vencimento'], 
            'numero': layout_dict['col_numero'], 
            'valor': layout_dict['col_valor'], 
            'pagador': layout_dict['col_pagador']
        }
        dados_processados = processar_dataframe_mapeado(df_bruto, mapa_atual)
        df_rev = pd.DataFrame(dados_processados)
        
        # Obtem clientes atuais
        clientes_db = listar_clientes_db(x_company_cnpj)
        lista_clientes_nomes = [c['nome'] for c in clientes_db]
        
        # Identifica novos clientes
        novos_clientes = list(set([row['pagador'] for _, row in df_rev.iterrows() if row['pagador'] not in lista_clientes_nomes]))
        
        # Retorna a previa
        titulos_lidos = df_rev.to_dict("records")
        return {
            "success": True, 
            "titulos": titulos_lidos,
            "novos_clientes_necessarios": novos_clientes
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class TituloConfirm(BaseModel):
    pagador: str
    numero: str
    vencimento: str
    valor: float

class ConfirmarImportacaoReq(BaseModel):
    titulos: List[TituloConfirm]
    # O frontend ja deve ter criado os novos clientes antes de chamar isso

@router.post("/confirm")
def confirmar_importacao(req: ConfirmarImportacaoReq, x_company_cnpj: str = Header(...)):
    # Normalização de datas antes de salvar
    titulos_dicts = []
    for t in req.titulos:
        d = t.dict()
        data_suja = str(d['vencimento']).strip()
        # Tenta normalizar D/M/YYYY para DD/MM/YYYY
        if '/' in data_suja:
            partes = data_suja.split('/')
            if len(partes) == 3:
                d['vencimento'] = f"{partes[0].zfill(2)}/{partes[1].zfill(2)}/{partes[2]}"
        titulos_dicts.append(d)
        
    salvar_dados_no_banco(x_company_cnpj, titulos_dicts)
    
    # Aqui vamos colocar a lógicas do item 7: "perguntar o que aconteceu com os títulos faltantes"
    # Por hora nós apenas salvamos os novos, o frontend fará essa checagem comparando a lista antiga
    return {"success": True, "message": "Importação concluída e títulos salvos."}

@router.get("/layouts")
def get_layouts(x_company_cnpj: str = Header(...)):
    mgr = Manager(x_company_cnpj)
    return {"layouts": mgr.obter_layouts_bancos()}

@router.post("/layouts")
def save_layout(layout: LayoutData, x_company_cnpj: str = Header(...)):
    mgr = Manager(x_company_cnpj)
    mapa = {
        'vencimento': layout.col_vencimento,
        'numero': layout.col_numero,
        'valor': layout.col_valor,
        'pagador': layout.col_pagador
    }
    mgr.salvar_layout_preferido(layout.nome_layout, mapa)
    return {"success": True, "message": "Layout salvo com sucesso."}

@router.delete("/layouts/{id}")
def delete_layout(id: int, x_company_cnpj: str = Header(...)):
    mgr = Manager(x_company_cnpj)
    mgr.excluir_layout_banco(id)
    return {"success": True, "message": "Layout deletado com sucesso."}

@router.post("/preview-pdf")
async def preview_new_pdf(file: UploadFile = File(...)):
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name
        
        df_bruto = ler_pdf_bruto(tmp_path)
        if df_bruto is None:
            raise HTTPException(status_code=400, detail="Não foi possível identificar colunas no PDF")
        
        # Envia os headers e algumas linhas de exemplo
        headers = [str(col) for col in df_bruto.columns.tolist() if str(col).strip() != '']
        sample_rows = df_bruto.head(5).astype(str).to_dict("records")
        return {"success": True, "headers": headers, "sample": sample_rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
