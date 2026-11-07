#!/usr/bin/env python3
"""Varredura de privacidade do dataset publicável (rodar antes de subir para Kaggle/HF)."""
import duckdb, re, json, sys
p = "data/publish/nfe_ncm_dataset.parquet"
con = duckdb.connect()
cols = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{p}')").fetchall()]
print("colunas:", cols)
forbidden = {"chave_acesso","cpf","cnpj","razao_social","inscricao_estadual","destinatario_nome","emitente_nome","numero_nota","serie","cnpj_destinatario","nome_destinatario"}
print("colunas proibidas presentes:", forbidden & set(cols))
n = con.execute(f"SELECT count(*) FROM read_parquet('{p}')").fetchone()[0]
print("linhas:", n)
# padroes em texto livre
checks = {
 "cnpj_formatado": r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}",
 "cnpj_14_digitos": r"(^|[^0-9])\d{14}([^0-9]|$)",
 "cpf_formatado": r"\d{3}\.\d{3}\.\d{3}-\d{2}",
 "cpf_11_digitos": r"(^|[^0-9])\d{11}([^0-9]|$)",
 "email": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
 "caminho_servidor": r"(/workspace|/home/|/root/|C:\\\\|/var/|/srv/)",
 "chave_44": r"\d{44}",
 "ventura": r"(?i)ventura",
}
for name, rx in checks.items():
    q = f"SELECT count(*) FROM read_parquet('{p}') WHERE regexp_matches(descricao_produto, '{rx}')"
    c = con.execute(q).fetchone()[0]
    print(f"{name}: {c}")
    if c and c < 50:
        ex = con.execute(f"SELECT descricao_produto FROM read_parquet('{p}') WHERE regexp_matches(descricao_produto, '{rx}') LIMIT 5").fetchall()
        for e in ex: print("   ex:", e[0][:140])
# amostra
print(con.execute(f"SELECT split, count(*) FROM read_parquet('{p}') GROUP BY 1 ORDER BY 1").fetchall())
