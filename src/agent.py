import os
import json
from google import genai
from google.genai import types
from src.database import get_connection, registrar_promessa

# Configure sua chave no ambiente
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

class NegociadorIA:
    def __init__(self, cnpj_credor):
        self.cnpj_credor = cnpj_credor
        self.empresa = "SERVWELD" if cnpj_credor == "11504286000169" else "Centro-Oeste"

    def _preparar_historico(self, nome_cliente):
        """Busca o que o cliente deve para munir a IA de fatos."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT numero_nf, valor, vencimento 
            FROM titulos 
            WHERE cnpj_cliente = ? AND situacao = 'VENCIDO' AND cnpj_credor = ?
        ''', (nome_cliente, self.cnpj_credor))
        titulos = cursor.fetchall()
        conn.close()

        resumo = f"Contexto: O cliente {nome_cliente} deve para a {self.empresa}:\n"
        total = 0
        for t in titulos:
            resumo += f"- NF {t['numero_nf']} de R$ {t['valor']:.2f} (Vencida em {t['vencimento']})\n"
            total += t['valor']
        resumo += f"Total: R$ {total:.2f}"
        return resumo, [t['numero_nf'] for t in titulos]

    def processar_resposta(self, nome_cliente, mensagem_cliente):
        contexto, nfs = self._preparar_historico(nome_cliente)
        
        prompt = f"""
        Você é o assistente financeiro da {self.empresa}.
        {contexto}
        
        O cliente disse: "{mensagem_cliente}"
        
        Sua tarefa:
        1. Seja cordial e profissional.
        2. Se ele prometer pagar, aceite se for em até 15 dias.
        3. Se ele pedir desconto, diga que não tem autonomia, mas pode parcelar em 2x.
        
        Responda ESTRITAMENTE em JSON:
        {{
            "mensagem_zap": "sua resposta aqui",
            "promessa_data": "AAAA-MM-DD ou null",
            "nf_afetada": "{nfs[0] if nfs else 'null'}"
        }}
        """

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[prompt],
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        
        dados = json.loads(response.text)
        
        # Se a IA detectou uma data, já salvamos no banco!
        if dados.get("promessa_data") and dados.get("nf_afetada"):
            registrar_promessa(dados["nf_afetada"], dados["promessa_data"])
            
        return dados