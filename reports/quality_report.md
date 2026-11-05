# Relatorio de qualidade de dados

Gerado em 2026-11-04 22:20 UTC a partir de `data/quality/*.json`.

Legenda: **pass** regra atendida; **warn** fora do esperado, registrado; **fail** bloqueia a camada; **info** medida sem limiar.

## Resumo por mes (silver)

| Mes | Notas | Itens | Rejeitadas | Duplicadas | NCM valido | q x unit = total | Soma itens = nota | Itens sem nota | Emitentes CPF |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2025-04 | 128.641 | 470.126 | 0 | 0 | 99,11% | 100,00% | 77,37% | 0 | 0 |
| 2025-05 | 143.760 | 523.639 | 0 | 0 | 99,13% | 100,00% | 84,46% | 0 | 0 |
| 2025-06 | 147.791 | 517.843 | 0 | 0 | 99,12% | 100,00% | 85,17% | 0 | 0 |
| 2025-07 | 173.981 | 569.088 | 0 | 0 | 99,22% | 100,00% | 85,92% | 0 | 0 |
| 2025-08 | 135.999 | 489.660 | 0 | 0 | 98,83% | 100,00% | 83,30% | 0 | 0 |
| 2025-09 | 148.686 | 554.569 | 0 | 0 | 98,78% | 100,00% | 83,90% | 0 | 0 |

## bronze / 2025-04  (pass 8, warn 0, fail 0, info 0)

| Checagem | Status | Observado | Esperado | Detalhes |
|---|---|---|---|---|
| `nota_schema_contract` | pass | True | igual ao contrato |  |
| `nota_row_count` | pass | 128641 | >= 1 |  |
| `nota_chave_presente` | pass | 0 | 0 |  |
| `item_schema_contract` | pass | True | igual ao contrato |  |
| `item_row_count` | pass | 470126 | >= 1 |  |
| `item_chave_presente` | pass | 0 | 0 |  |
| `evento_schema_contract` | pass | True | igual ao contrato |  |
| `evento_row_count` | pass | 0 | pode ser 0 (arquivo vazio na fonte) |  |

## bronze / 2025-05  (pass 8, warn 0, fail 0, info 0)

| Checagem | Status | Observado | Esperado | Detalhes |
|---|---|---|---|---|
| `nota_schema_contract` | pass | True | igual ao contrato |  |
| `nota_row_count` | pass | 143760 | >= 1 |  |
| `nota_chave_presente` | pass | 0 | 0 |  |
| `item_schema_contract` | pass | True | igual ao contrato |  |
| `item_row_count` | pass | 523639 | >= 1 |  |
| `item_chave_presente` | pass | 0 | 0 |  |
| `evento_schema_contract` | pass | True | igual ao contrato |  |
| `evento_row_count` | pass | 0 | pode ser 0 (arquivo vazio na fonte) |  |

## bronze / 2025-06  (pass 8, warn 0, fail 0, info 0)

| Checagem | Status | Observado | Esperado | Detalhes |
|---|---|---|---|---|
| `nota_schema_contract` | pass | True | igual ao contrato |  |
| `nota_row_count` | pass | 147791 | >= 1 |  |
| `nota_chave_presente` | pass | 0 | 0 |  |
| `item_schema_contract` | pass | True | igual ao contrato |  |
| `item_row_count` | pass | 517843 | >= 1 |  |
| `item_chave_presente` | pass | 0 | 0 |  |
| `evento_schema_contract` | pass | True | igual ao contrato |  |
| `evento_row_count` | pass | 0 | pode ser 0 (arquivo vazio na fonte) |  |

## bronze / 2025-07  (pass 8, warn 0, fail 0, info 0)

| Checagem | Status | Observado | Esperado | Detalhes |
|---|---|---|---|---|
| `nota_schema_contract` | pass | True | igual ao contrato |  |
| `nota_row_count` | pass | 173981 | >= 1 |  |
| `nota_chave_presente` | pass | 0 | 0 |  |
| `item_schema_contract` | pass | True | igual ao contrato |  |
| `item_row_count` | pass | 569088 | >= 1 |  |
| `item_chave_presente` | pass | 0 | 0 |  |
| `evento_schema_contract` | pass | True | igual ao contrato |  |
| `evento_row_count` | pass | 0 | pode ser 0 (arquivo vazio na fonte) |  |

## bronze / 2025-08  (pass 8, warn 0, fail 0, info 0)

| Checagem | Status | Observado | Esperado | Detalhes |
|---|---|---|---|---|
| `nota_schema_contract` | pass | True | igual ao contrato |  |
| `nota_row_count` | pass | 135999 | >= 1 |  |
| `nota_chave_presente` | pass | 0 | 0 |  |
| `item_schema_contract` | pass | True | igual ao contrato |  |
| `item_row_count` | pass | 489660 | >= 1 |  |
| `item_chave_presente` | pass | 0 | 0 |  |
| `evento_schema_contract` | pass | True | igual ao contrato |  |
| `evento_row_count` | pass | 0 | pode ser 0 (arquivo vazio na fonte) |  |

## bronze / 2025-09  (pass 8, warn 0, fail 0, info 0)

| Checagem | Status | Observado | Esperado | Detalhes |
|---|---|---|---|---|
| `nota_schema_contract` | pass | True | igual ao contrato |  |
| `nota_row_count` | pass | 148686 | >= 1 |  |
| `nota_chave_presente` | pass | 0 | 0 |  |
| `item_schema_contract` | pass | True | igual ao contrato |  |
| `item_row_count` | pass | 554569 | >= 1 |  |
| `item_chave_presente` | pass | 0 | 0 |  |
| `evento_schema_contract` | pass | True | igual ao contrato |  |
| `evento_row_count` | pass | 0 | pode ser 0 (arquivo vazio na fonte) |  |

## gold / all  (pass 9, warn 0, fail 0, info 0)

| Checagem | Status | Observado | Esperado | Detalhes |
|---|---|---|---|---|
| `fato_item_pk_unica` | pass | 0 | 0 | {"linhas": 3124925} |
| `fato_item_fk_dim_ncm` | pass | 0 | 0 |  |
| `dim_ncm_fk_dim_capitulo` | pass | 0 | 0 |  |
| `fato_item_fk_fato_nota` | pass | 0 | 0 |  |
| `conservacao_silver_para_gold` | pass | {"silver": [3124925, 46528296270.74], "gold": [3124925, 46528296270.74]} | iguais |  |
| `agg_ncm_mes_consistente` | pass | {"agg": 44926929747.51, "fato": 44926929747.51} | iguais |  |
| `ml_sem_identificadores` | pass | [] | [] |  |
| `ml_linhas` | pass | 3094298 | > 0 |  |
| `fato_nota_cpf_mascarado` | pass | 0 | 0 |  |

## silver / 2025-04  (pass 12, warn 1, fail 0, info 6)

| Checagem | Status | Observado | Esperado | Detalhes |
|---|---|---|---|---|
| `nota_rejeitadas` | pass | 0 | < 0,5% das linhas | {"pct": 0.0, "por_motivo": {}} |
| `nota_duplicadas_removidas` | info | 0 | informativo | {"chave": ["chave_acesso"]} |
| `item_rejeitadas` | pass | 0 | < 0,5% das linhas | {"pct": 0.0, "por_motivo": {}} |
| `item_duplicadas_removidas` | info | 0 | informativo | {"chave": ["chave_acesso", "numero_produto"]} |
| `item_pk_unica` | pass | 0 | 0 duplicatas | {"linhas": 470126} |
| `nota_pk_unica` | pass | 0 | 0 duplicatas | {"linhas": 128641} |
| `item_chave_44_digitos` | pass | 0 | 0 |  |
| `item_ncm_valido_pct` | pass | 99.1079 | >= 97% | {"validos": 465932, "invalidos": 4194, "ncm_distintos": 5018, "ncm_raw_por_tamanho": {"len=8": 372790, "len=7": 93198, "sentinela -1": 4129, "len=5": 8, "len=2": 1}} |
| `item_cfop_valido_pct` | pass | 100.0 | >= 99,9% | {"invalidos": 0} |
| `item_sem_nota` | pass | 0 | 0 |  |
| `nota_sem_item` | warn | 4296 | 0 |  |
| `item_qtd_x_unitario_igual_total` | pass | 100.0 | >= 99% | {"divergentes": 0} |
| `soma_itens_vs_valor_nota` | info | 77.367 | divergencia esperada: frete, desconto, IPI e ICMS-ST entram no total da nota e nao nos itens | {"notas_comparadas": 124345, "batem": 96202, "itens_maior_que_nota (desconto)": 9764, "itens_menor_que_nota (frete/impostos)": 18379, "valor_total_notas": 5757392745.68, "valor_total_itens": 6088528126.31} |
| `item_valores_nao_negativos` | pass | 0 | 0 |  |
| `item_data_emissao_no_mes` | pass | 100.0 | >= 95% | {"fora_do_mes": 0} |
| `item_descricao_vazia` | info | 47 | informativo (excluidos do dataset de ML) |  |
| `nota_emitente_pessoa_fisica` | info | 0 | informativo (LGPD) |  |
| `item_nulos_por_coluna` | info | {"ncm_descricao": 5.08, "orgao_codigo": 80.17, "emitente_ie": 4.43, "unidade": 0.12, "destinatario_uf": 0.0} | informativo ('Sem informação' e '-1' virarem NULL e intencional) |  |
| `item_reconciliacao_bronze` | pass | 470126 | 470126 + rejeitadas + duplicadas |  |

## silver / 2025-05  (pass 12, warn 1, fail 0, info 6)

| Checagem | Status | Observado | Esperado | Detalhes |
|---|---|---|---|---|
| `nota_rejeitadas` | pass | 0 | < 0,5% das linhas | {"pct": 0.0, "por_motivo": {}} |
| `nota_duplicadas_removidas` | info | 0 | informativo | {"chave": ["chave_acesso"]} |
| `item_rejeitadas` | pass | 0 | < 0,5% das linhas | {"pct": 0.0, "por_motivo": {}} |
| `item_duplicadas_removidas` | info | 0 | informativo | {"chave": ["chave_acesso", "numero_produto"]} |
| `item_pk_unica` | pass | 0 | 0 duplicatas | {"linhas": 523639} |
| `nota_pk_unica` | pass | 0 | 0 duplicatas | {"linhas": 143760} |
| `item_chave_44_digitos` | pass | 0 | 0 |  |
| `item_ncm_valido_pct` | pass | 99.1288 | >= 97% | {"validos": 519077, "invalidos": 4562, "ncm_distintos": 5160, "ncm_raw_por_tamanho": {"len=8": 413061, "len=7": 106236, "sentinela -1": 4290, "len=5": 52}} |
| `item_cfop_valido_pct` | pass | 100.0 | >= 99,9% | {"invalidos": 0} |
| `item_sem_nota` | pass | 0 | 0 |  |
| `nota_sem_item` | warn | 39 | 0 |  |
| `item_qtd_x_unitario_igual_total` | pass | 100.0 | >= 99% | {"divergentes": 0} |
| `soma_itens_vs_valor_nota` | info | 84.4616 | divergencia esperada: frete, desconto, IPI e ICMS-ST entram no total da nota e nao nos itens | {"notas_comparadas": 143721, "batem": 121389, "itens_maior_que_nota (desconto)": 11587, "itens_menor_que_nota (frete/impostos)": 10745, "valor_total_notas": 7055023456.75, "valor_total_itens": 7305836451.11} |
| `item_valores_nao_negativos` | pass | 0 | 0 |  |
| `item_data_emissao_no_mes` | pass | 100.0 | >= 95% | {"fora_do_mes": 0} |
| `item_descricao_vazia` | info | 40 | informativo (excluidos do dataset de ML) |  |
| `nota_emitente_pessoa_fisica` | info | 0 | informativo (LGPD) |  |
| `item_nulos_por_coluna` | info | {"ncm_descricao": 5.21, "orgao_codigo": 81.07, "emitente_ie": 4.55, "unidade": 0.11, "destinatario_uf": 0.0} | informativo ('Sem informação' e '-1' virarem NULL e intencional) |  |
| `item_reconciliacao_bronze` | pass | 523639 | 523639 + rejeitadas + duplicadas |  |

## silver / 2025-06  (pass 12, warn 1, fail 0, info 6)

| Checagem | Status | Observado | Esperado | Detalhes |
|---|---|---|---|---|
| `nota_rejeitadas` | pass | 0 | < 0,5% das linhas | {"pct": 0.0, "por_motivo": {}} |
| `nota_duplicadas_removidas` | info | 0 | informativo | {"chave": ["chave_acesso"]} |
| `item_rejeitadas` | pass | 0 | < 0,5% das linhas | {"pct": 0.0, "por_motivo": {}} |
| `item_duplicadas_removidas` | info | 0 | informativo | {"chave": ["chave_acesso", "numero_produto"]} |
| `item_pk_unica` | pass | 0 | 0 duplicatas | {"linhas": 517843} |
| `nota_pk_unica` | pass | 0 | 0 duplicatas | {"linhas": 147791} |
| `item_chave_44_digitos` | pass | 0 | 0 |  |
| `item_ncm_valido_pct` | pass | 99.1219 | >= 97% | {"validos": 513296, "invalidos": 4547, "ncm_distintos": 5076, "ncm_raw_por_tamanho": {"len=8": 410084, "len=7": 103448, "sentinela -1": 4297, "len=5": 12, "len=2": 2}} |
| `item_cfop_valido_pct` | pass | 100.0 | >= 99,9% | {"invalidos": 0} |
| `item_sem_nota` | pass | 0 | 0 |  |
| `nota_sem_item` | warn | 5 | 0 |  |
| `item_qtd_x_unitario_igual_total` | pass | 100.0 | >= 99% | {"divergentes": 0} |
| `soma_itens_vs_valor_nota` | info | 85.165 | divergencia esperada: frete, desconto, IPI e ICMS-ST entram no total da nota e nao nos itens | {"notas_comparadas": 147786, "batem": 125862, "itens_maior_que_nota (desconto)": 11321, "itens_menor_que_nota (frete/impostos)": 10603, "valor_total_notas": 6279885552.11, "valor_total_itens": 8460040896.87} |
| `item_valores_nao_negativos` | pass | 0 | 0 |  |
| `item_data_emissao_no_mes` | pass | 100.0 | >= 95% | {"fora_do_mes": 0} |
| `item_descricao_vazia` | info | 68 | informativo (excluidos do dataset de ML) |  |
| `nota_emitente_pessoa_fisica` | info | 0 | informativo (LGPD) |  |
| `item_nulos_por_coluna` | info | {"ncm_descricao": 4.98, "orgao_codigo": 79.0, "emitente_ie": 3.85, "unidade": 0.12, "destinatario_uf": 0.0} | informativo ('Sem informação' e '-1' virarem NULL e intencional) |  |
| `item_reconciliacao_bronze` | pass | 517843 | 517843 + rejeitadas + duplicadas |  |

## silver / 2025-07  (pass 13, warn 0, fail 0, info 6)

| Checagem | Status | Observado | Esperado | Detalhes |
|---|---|---|---|---|
| `nota_rejeitadas` | pass | 0 | < 0,5% das linhas | {"pct": 0.0, "por_motivo": {}} |
| `nota_duplicadas_removidas` | info | 0 | informativo | {"chave": ["chave_acesso"]} |
| `item_rejeitadas` | pass | 0 | < 0,5% das linhas | {"pct": 0.0, "por_motivo": {}} |
| `item_duplicadas_removidas` | info | 0 | informativo | {"chave": ["chave_acesso", "numero_produto"]} |
| `item_pk_unica` | pass | 0 | 0 duplicatas | {"linhas": 569088} |
| `nota_pk_unica` | pass | 0 | 0 duplicatas | {"linhas": 173981} |
| `item_chave_44_digitos` | pass | 0 | 0 |  |
| `item_ncm_valido_pct` | pass | 99.2154 | >= 97% | {"validos": 564623, "invalidos": 4465, "ncm_distintos": 5241, "ncm_raw_por_tamanho": {"len=8": 463974, "len=7": 100874, "sentinela -1": 4220, "len=5": 14, "len=2": 6}} |
| `item_cfop_valido_pct` | pass | 100.0 | >= 99,9% | {"invalidos": 0} |
| `item_sem_nota` | pass | 0 | 0 |  |
| `nota_sem_item` | pass | 0 | 0 |  |
| `item_qtd_x_unitario_igual_total` | pass | 100.0 | >= 99% | {"divergentes": 0} |
| `soma_itens_vs_valor_nota` | info | 85.9192 | divergencia esperada: frete, desconto, IPI e ICMS-ST entram no total da nota e nao nos itens | {"notas_comparadas": 173981, "batem": 149483, "itens_maior_que_nota (desconto)": 12600, "itens_menor_que_nota (frete/impostos)": 11898, "valor_total_notas": 6274992533.04, "valor_total_itens": 7587935341.47} |
| `item_valores_nao_negativos` | pass | 0 | 0 |  |
| `item_data_emissao_no_mes` | pass | 100.0 | >= 95% | {"fora_do_mes": 0} |
| `item_descricao_vazia` | info | 54 | informativo (excluidos do dataset de ML) |  |
| `nota_emitente_pessoa_fisica` | info | 0 | informativo (LGPD) |  |
| `item_nulos_por_coluna` | info | {"ncm_descricao": 5.76, "orgao_codigo": 82.05, "emitente_ie": 3.45, "unidade": 0.12, "destinatario_uf": 0.0} | informativo ('Sem informação' e '-1' virarem NULL e intencional) |  |
| `item_reconciliacao_bronze` | pass | 569088 | 569088 + rejeitadas + duplicadas |  |

## silver / 2025-08  (pass 12, warn 1, fail 0, info 6)

| Checagem | Status | Observado | Esperado | Detalhes |
|---|---|---|---|---|
| `nota_rejeitadas` | pass | 0 | < 0,5% das linhas | {"pct": 0.0, "por_motivo": {}} |
| `nota_duplicadas_removidas` | info | 0 | informativo | {"chave": ["chave_acesso"]} |
| `item_rejeitadas` | pass | 0 | < 0,5% das linhas | {"pct": 0.0, "por_motivo": {}} |
| `item_duplicadas_removidas` | info | 0 | informativo | {"chave": ["chave_acesso", "numero_produto"]} |
| `item_pk_unica` | pass | 0 | 0 duplicatas | {"linhas": 489660} |
| `nota_pk_unica` | pass | 0 | 0 duplicatas | {"linhas": 135999} |
| `item_chave_44_digitos` | pass | 0 | 0 |  |
| `item_ncm_valido_pct` | pass | 98.8278 | >= 97% | {"validos": 483920, "invalidos": 5740, "ncm_distintos": 5235, "ncm_raw_por_tamanho": {"len=8": 404676, "len=7": 79451, "sentinela -1": 5532, "len=5": 1}} |
| `item_cfop_valido_pct` | pass | 100.0 | >= 99,9% | {"invalidos": 0} |
| `item_sem_nota` | pass | 0 | 0 |  |
| `nota_sem_item` | warn | 4 | 0 |  |
| `item_qtd_x_unitario_igual_total` | pass | 100.0 | >= 99% | {"divergentes": 0} |
| `soma_itens_vs_valor_nota` | info | 83.3023 | divergencia esperada: frete, desconto, IPI e ICMS-ST entram no total da nota e nao nos itens | {"notas_comparadas": 135995, "batem": 113287, "itens_maior_que_nota (desconto)": 11301, "itens_menor_que_nota (frete/impostos)": 11407, "valor_total_notas": 5448880688.3, "valor_total_itens": 6130858926.3} |
| `item_valores_nao_negativos` | pass | 0 | 0 |  |
| `item_data_emissao_no_mes` | pass | 100.0 | >= 95% | {"fora_do_mes": 0} |
| `item_descricao_vazia` | info | 59 | informativo (excluidos do dataset de ML) |  |
| `nota_emitente_pessoa_fisica` | info | 0 | informativo (LGPD) |  |
| `item_nulos_por_coluna` | info | {"ncm_descricao": 6.18, "orgao_codigo": 83.04, "emitente_ie": 3.5, "unidade": 0.13, "destinatario_uf": 0.0} | informativo ('Sem informação' e '-1' virarem NULL e intencional) |  |
| `item_reconciliacao_bronze` | pass | 489660 | 489660 + rejeitadas + duplicadas |  |

## silver / 2025-09  (pass 13, warn 0, fail 0, info 6)

| Checagem | Status | Observado | Esperado | Detalhes |
|---|---|---|---|---|
| `nota_rejeitadas` | pass | 0 | < 0,5% das linhas | {"pct": 0.0, "por_motivo": {}} |
| `nota_duplicadas_removidas` | info | 0 | informativo | {"chave": ["chave_acesso"]} |
| `item_rejeitadas` | pass | 0 | < 0,5% das linhas | {"pct": 0.0, "por_motivo": {}} |
| `item_duplicadas_removidas` | info | 0 | informativo | {"chave": ["chave_acesso", "numero_produto"]} |
| `item_pk_unica` | pass | 0 | 0 duplicatas | {"linhas": 554569} |
| `nota_pk_unica` | pass | 0 | 0 duplicatas | {"linhas": 148686} |
| `item_chave_44_digitos` | pass | 0 | 0 |  |
| `item_ncm_valido_pct` | pass | 98.7758 | >= 97% | {"validos": 547780, "invalidos": 6789, "ncm_distintos": 5456, "ncm_raw_por_tamanho": {"len=8": 462086, "len=7": 85787, "sentinela -1": 6696}} |
| `item_cfop_valido_pct` | pass | 100.0 | >= 99,9% | {"invalidos": 0} |
| `item_sem_nota` | pass | 0 | 0 |  |
| `nota_sem_item` | pass | 0 | 0 |  |
| `item_qtd_x_unitario_igual_total` | pass | 100.0 | >= 99% | {"divergentes": 0} |
| `soma_itens_vs_valor_nota` | info | 83.9043 | divergencia esperada: frete, desconto, IPI e ICMS-ST entram no total da nota e nao nos itens | {"notas_comparadas": 148686, "batem": 124754, "itens_maior_que_nota (desconto)": 13121, "itens_menor_que_nota (frete/impostos)": 10811, "valor_total_notas": 8322421934.1, "valor_total_itens": 10955096528.68} |
| `item_valores_nao_negativos` | pass | 0 | 0 |  |
| `item_data_emissao_no_mes` | pass | 100.0 | >= 95% | {"fora_do_mes": 0} |
| `item_descricao_vazia` | info | 62 | informativo (excluidos do dataset de ML) |  |
| `nota_emitente_pessoa_fisica` | info | 0 | informativo (LGPD) |  |
| `item_nulos_por_coluna` | info | {"ncm_descricao": 5.81, "orgao_codigo": 82.95, "emitente_ie": 2.7, "unidade": 0.11, "destinatario_uf": 0.0} | informativo ('Sem informação' e '-1' virarem NULL e intencional) |  |
| `item_reconciliacao_bronze` | pass | 554569 | 554569 + rejeitadas + duplicadas |  |
