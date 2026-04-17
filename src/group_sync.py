import sqlite3
import os
from src.database import conectar, carregar_todas_unidades_db
from src.evolution_controller import EvolutionController

def sincronizar_grupo_operadores(cnpj_base=None):
    """
    Sincroniza a lista de 'operador_whatsapp' de todas as unidades com o grupo unificado da Analu.
    Garante que os números cadastrados na configuração estejam no grupo, e remove os que não estão mais.
    
    1. Lê todos os operadores de todas as unidades.
    2. Lê o ID do grupo na tabela config_global. Se não existir, cria o grupo.
    3. Atualiza participantes via EvolutionController.
    """
    try:
        conn = conectar()
        c = conn.cursor()
        
        # 1. Recuperar todos os operadores de todas as unidades
        print("[SYNC GRUPO] Iniciando coleta de operadores...")
        unidades = carregar_todas_unidades_db()
        todos_operadores = set()
        instancia_ativa = None
        conf_ativa = None
        
        for u in unidades:
            cnpj = str(u['empresa_cnpj']).replace('.', '').replace('/', '').replace('-', '')
            print(f"   -> Verificando unidade {u['empresa_nome']} ({cnpj})...")
            try:
                conn_u = conectar(cnpj)
                res = conn_u.cursor().execute("SELECT * FROM config LIMIT 1").fetchone()
                
                if res:
                    res_dict = dict(res)
                    op_raw = res_dict.get('operador_whatsapp')
                    if op_raw:
                        nums = [n.strip() for n in op_raw.split(';') if n.strip()]
                        for n in nums: 
                            print(f"      + Operador encontrado: {n}")
                            todos_operadores.add(n)
                    
                    # Aproveitamos para pegar uma instância ativa para usar a API
                    if not conf_ativa and res_dict.get('evo_url'):
                        conf_ativa = res_dict
                        instancia_ativa = cnpj
                        print(f"      * Instância '{cnpj}' selecionada para conexão API.")
                        
                conn_u.close()
            except Exception as e:
                print(f"      [ERRO] Falha ao ler unidade {cnpj}: {e}")
                
        # 2. Se não houver config ativa, nem operadores, aborta
        if not conf_ativa:
            print("[SYNC GRUPO] ABORTADO: Nenhuma configuração de API (URL/Key) encontrada nas unidades.")
            return
            
        if not todos_operadores:
            print("[SYNC GRUPO] ABORTADO: Nenhum número de operador configurado nas unidades.")
            return
            
        evo = EvolutionController(conf_ativa, instancia_ativa)
        
        # 3. Ler JID do grupo
        res_global = c.execute("SELECT grupo_relatorio_jid FROM config_global WHERE id = 1").fetchone()
        group_jid = dict(res_global).get('grupo_relatorio_jid') if res_global else None
        
        # 4. Criar grupo se não existir
        if not group_jid:
            print("[SYNC GRUPO] Criando novo grupo 'Relatório da Analu'...")
            grupo = evo.criar_grupo(
                subject="Relatório da Analu",
                participants=list(todos_operadores),
                description="Grupo automático para recebimento de relatórios diários e notificações."
            )
            if grupo and grupo.get("id"):
                group_jid = grupo.get("id")
                c.execute("UPDATE config_global SET grupo_relatorio_jid = ? WHERE id = 1", (group_jid,))
                conn.commit()
                print(f"[SYNC GRUPO] Grupo criado com ID: {group_jid}")
            else:
                print(f"[SYNC GRUPO] FALHA CRÍTICA: API não criou o grupo. Resposta: {grupo}")
                return
        
        # 5. Sincronizar Participantes
        print(f"[SYNC GRUPO] Sincronizando participantes para o grupo {group_jid}...")
        detalhes = evo.buscar_detalhes_grupo(group_jid)
        if not detalhes:
            print("[SYNC GRUPO] Erro ao buscar detalhes do grupo JID via API.")
            return
            
        # O retorno da API varia se é inviteInfo ou groupMetadata. 
        # Geralmente tem a chave `participants` com objetos `{ "id": "number@s.whatsapp.net", ... }`
        participantes_atuais_jids = [p.get('id', '') for p in detalhes.get('participants', [])]
        
        jids_alvo = set()
        for op in todos_operadores:
            jid_valido = evo.buscar_jid_valido(op)
            if jid_valido and "@g.us" not in jid_valido:
                jids_alvo.add(jid_valido)
                
        adicionar = list(jids_alvo.difference(set(participantes_atuais_jids)))
        # Evita remover o bot (descobre o próprio JID ou remove apenas os que não são operadores)
        remover = [p for p in participantes_atuais_jids if p not in jids_alvo and "@s.whatsapp.net" in p]
        
        if adicionar:
            print(f"[SYNC GRUPO] Adicionando novos membros: {adicionar}")
            evo.atualizar_participantes_grupo(group_jid, "add", adicionar)
            
        if remover:
            # Filtro extra para não remover o dono (bot) acidentalmente
            # O dono geralmente é quem criou o grupo.
            print(f"[SYNC GRUPO] Membros obsoletos identificados: {remover} (A remoção automática está habilitada)")
            evo.atualizar_participantes_grupo(group_jid, "remove", remover)

        print("[SYNC GRUPO] Sincronização finalizada com sucesso.")

    except Exception as e:
        print(f"[SYNC GRUPO] ERRO GERAL: {e}")
    finally:
        try: conn.close()
        except: pass

if __name__ == "__main__":
    sincronizar_grupo_operadores()
