import os
import sqlite3
import shutil

class FiscalRepository:
    def __init__(self, db_dir="/app/data", repo_dir="/app/data/repository_v2"):
        self.db_dir = db_dir
        self.repo_dir = repo_dir
        os.makedirs(self.repo_dir, exist_ok=True)
        
    def _limpar_nome(self, nome):
        return "".join([c for c in nome if c.isalnum() or c in (' ', '_', '-')]).strip()

    def organizar_arquivo(self, cnpj_empresa, cnpj_cliente, nome_cliente, tipo_doc, num_nf, fpath_origem):
        """Move o arquivo para a hierarquia estruturada e atualiza o banco"""
        if not os.path.exists(fpath_origem): return None
        
        cnpj_cli_limpo = self._limpar_nome(str(cnpj_cliente))
        nome_cli_limpo = self._limpar_nome(str(nome_cliente)).replace(" ", "_")
        nf_str = str(num_nf).lstrip('0')
        tipo_clean = tipo_doc.lower()
        
        # Mapeia os tipos detectados para as pastas propostas
        pasta_tipo = "outros"
        if tipo_clean == "nf-e": pasta_tipo = "nf-e"
        elif tipo_clean == "nf-s": pasta_tipo = "nfs"
        elif tipo_clean == "fatura-locacao": pasta_tipo = "locacao"
        elif tipo_clean == "boleto": pasta_tipo = "boleto"
        
        # Estrutura: /repository_v2/{CNPJ}_{NOME}/{TIPO}/{NF}/
        rel_dir = os.path.join(f"{cnpj_cli_limpo}_{nome_cli_limpo}", pasta_tipo, nf_str)
        dest_dir = os.path.join(self.repo_dir, rel_dir)
        os.makedirs(dest_dir, exist_ok=True)
        
        filename = os.path.basename(fpath_origem)
        dest_path = os.path.join(dest_dir, filename)
        
        # Move arquivo (sobrescreve se existir)
        shutil.copy2(fpath_origem, dest_path)
        
        rel_path = os.path.join(rel_dir, filename).replace("\\", "/")
        
        # Atualiza o banco
        self._atualizar_banco(cnpj_empresa, cnpj_cli_limpo, nf_str, tipo_doc, rel_path, nome_cliente)
        
        return dest_path

    def _atualizar_banco(self, cnpj_empresa, cnpj_cliente, num_nf, tipo, pasta_repo, nome_cli):
        db_path = os.path.join(self.db_dir, f"db_{cnpj_empresa}.db")
        if not os.path.exists(db_path): return
        
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        try:
            # Procura se o arquivo já tá registrado pelo rel_path ou filename similar
            c.execute("SELECT id FROM documentos_fiscais WHERE cnpj_cliente=? AND num_nf=? AND tipo=? AND fpath_local LIKE ?", 
                      (cnpj_cliente, num_nf, tipo, f"%{os.path.basename(pasta_repo)}%"))
            row = c.fetchone()
            
            if row:
                c.execute("UPDATE documentos_fiscais SET pasta_repo=?, nome_cliente=? WHERE id=?", 
                          (pasta_repo, nome_cli, row[0]))
            else:
                agora = __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                c.execute("""
                    INSERT INTO documentos_fiscais 
                    (cnpj_cliente, num_nf, tipo, fpath_local, created_at, pasta_repo, nome_cliente)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (cnpj_cliente, num_nf, tipo, os.path.join(self.repo_dir, pasta_repo), agora, pasta_repo, nome_cli))
            conn.commit()
        except Exception as e:
            print(f"Erro atualizando repo DB (CNPJ Emp: {cnpj_empresa}, CNPJ Cli: {cnpj_cliente}, NF: {num_nf}): {e}")
            import traceback
            traceback.print_exc()
        finally:
            conn.close()

    def buscar_documentos(self, cnpj_empresa, cnpj_cliente, num_nf):
        """Retorna todos os paths absolutos (PDF/XML) pra uma NF de um cliente"""
        db_path = os.path.join(self.db_dir, f"db_{cnpj_empresa}.db")
        if not os.path.exists(db_path): return []
        
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        arquivos = []
        try:
            nf_str = str(num_nf).lstrip('0')
            
            # --- FASE 0: Busca na nova coluna estruturada ---
            # Se for NFS, ele deve levar o material e o boleto junto.
            # A lógica de dump/vínculo já marcou essas NFs.
            
            c.execute("""
                SELECT pasta_repo FROM documentos_fiscais 
                WHERE cnpj_cliente=? AND pasta_repo IS NOT NULL
                AND (num_nf=? OR nfs_vinculada=?)
            """, (cnpj_cliente, nf_str, nf_str))
            
            for row in c.fetchall():
                if row[0]:
                    full_path = os.path.join(self.repo_dir, row[0])
                    if os.path.exists(full_path):
                        arquivos.append(full_path)
                        
            # TODO: Add logic to fetch by timeframe if requested
                        
        except Exception as e:
            print(f"Erro buscando no repo DB: {e}")
        finally:
            conn.close()
            
        return arquivos
