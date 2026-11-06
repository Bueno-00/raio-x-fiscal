# Dataset card: NF-e públicas, descrição de produto -> NCM

**Português** · [English](DATASET_CARD.en.md)

Arquivos gerados por `make publish` em `data/publish/` (não versionados; a FASE 2 publica no Kaggle e
no Hugging Face). Este card acompanha os arquivos.

## Resumo

Itens de notas fiscais eletrônicas de compras do governo federal brasileiro, publicados pelo Portal da
Transparência (CGU), com a **descrição livre do produto** escrita pelo fornecedor e o **NCM de 8
dígitos** declarado por ele. Tarefa principal: classificar a descrição no NCM (8 dígitos) ou no capítulo
(2 dígitos). Tarefas secundárias possíveis: detecção de inconsistência de classificação, normalização de
descrições, estudo de gasto público por categoria.

- Linhas: **3.094.298** itens (seis meses, 2025-04 a 2025-09), 7.381 NCMs, 96 capítulos,
  ~900 mil descrições normalizadas distintas.
- Idioma: português do Brasil (texto de fornecedor: abreviações, maiúsculas, erros de digitação).
- Formatos: Parquet (ZSTD) e CSV gzip, mesmas colunas.

## Fonte e licença

- Portal da Transparência, conjunto "Notas Fiscais", download mensal
  (`https://portaldatransparencia.gov.br/download-de-dados/notas-fiscais/AAAAMM`), arquivos
  `NotaFiscal` e `NotaFiscalItem`. Dados abertos do governo federal (catálogo dados.gov.br: ODbL,
  a confirmar na página do conjunto no momento da publicação). Este dataset derivado mantém a mesma
  licença dos dados de origem; o código que o gera é MIT.
- Citação sugerida: Controladoria-Geral da União, Portal da Transparência, Notas Fiscais Eletrônicas
  (acesso em novembro de 2026); derivado por Rafael Bueno, repositório `raio-x-fiscal`.

## Privacidade (LGPD)

Removidos: chave de acesso da NF-e (contém o CNPJ do emitente), CPF/CNPJ e razão social do emitente,
inscrição estadual, CNPJ e nome do destinatário, número e série da nota. Mantidos: descrição do produto,
NCM e descrição oficial do NCM, CFOP, unidade, quantidade, valores, UF do emitente e do destinatário,
mês e data de emissão. `item_id` é um md5 de (chave de acesso, número do item), não reversível sem a
chave. A descrição do produto é texto livre do fornecedor e pode, em raros casos, conter nomes de marca
ou de pessoas; nenhum filtro adicional foi aplicado além do que a fonte publica.

## Colunas

| Coluna | Tipo | Descrição |
|---|---|---|
| `item_id` | string | md5(chave_acesso, numero_produto); identificador estável do item |
| `split` | string | `train` (2025-04 a 2025-07), `valid` (2025-08), `test` (2025-09) |
| `mes_referencia` | string | AAAA-MM do arquivo de origem |
| `descricao_produto` | string | descrição livre do fornecedor, como publicada |
| `descricao_normalizada` | string | minúsculas, sem acento, só `[a-z0-9]` separados por espaço |
| `ncm_codigo` | string | NCM de 8 dígitos, zero à esquerda restaurado (**rótulo**) |
| `capitulo` | string | 2 primeiros dígitos do NCM (rótulo grosso) |
| `posicao` | string | 4 primeiros dígitos do NCM |
| `ncm_descricao` | string | descrição oficial do NCM mais frequente para o código |
| `cfop` | string | CFOP de 4 dígitos (NULL se inválido) |
| `unidade` | string | unidade comercial em maiúsculas (`UNIDAD`, `KG`, `PEÇA`, ...) |
| `quantidade` | decimal(18,4) | quantidade do item |
| `valor_unitario` | decimal(18,4) | valor unitário em BRL |
| `valor_total` | decimal(18,2) | valor total do item em BRL |
| `emitente_uf` | string | UF do fornecedor |
| `destinatario_uf` | string | UF do órgão comprador |
| `seen_in_train` | bool | para `valid`/`test`: a `descricao_normalizada` existe no `train` (NULL no treino) |

## Splits e protocolo recomendado

Split **temporal**: treinar em meses anteriores, testar no mais recente. O dataset entrega todos os
itens (com repetição) para que cada usuário escolha a política de deduplicação; a recomendada é a do
baseline:

1. treino colapsado a uma linha por `descricao_normalizada`, rótulo = NCM mais frequente;
2. reportar o teste em quatro cortes: todos os itens, descrições únicas, itens com
   `seen_in_train = false`, e descrições únicas não vistas (número honesto de generalização).

Ruído de rótulo conhecido: 3,6% das descrições de treino aparecem com mais de um NCM, concentrando 26%
dos itens; entre itens de teste com descrição já vista, o NCM coincide em 86,5% dos casos. O rótulo é o
que o fornecedor declarou, não uma verdade auditada.

## Baseline

<!-- CARD_BASELINE_START -->
TF-IDF (palavra 1-2 + caractere 3-5, 400 mil dimensões) + LinearSVC hierárquico (capítulo, depois NCM
dentro do capítulo), treino 2025-04 a 2025-07, teste 2025-09:

| Corte do teste | Capítulo top-1 / top-5 | NCM top-1 / top-5 | NCM F1 macro |
|---|---:|---:|---:|
| Todos os itens (547.718) | 89,0% / 96,0% | 77,3% / 87,7% | 38,1% |
| Descrições únicas não vistas (126.723) | 79,7% / 92,4% | 60,0% / 76,1% | 26,5% |

Detalhes e comparação com lookup exato e classe majoritária em `reports/ml_results.md`.
<!-- CARD_BASELINE_END -->

## Limitações e vieses

- Cobertura: só compras do governo federal, com forte peso de material médico-hospitalar (capítulo 90),
  medicamentos (30), alimentos (07, 08), livros (49), máquinas e eletrônicos (84, 85). Não representa
  o varejo nem a indústria em geral.
- Rótulo ruidoso (acima). Descrições muito curtas ("VENDA", "SERVICO") são legitimamente ambíguas.
- Seis meses de um único ano; sazonalidade e mudanças de tabela NCM não estão cobertas.
- Valores são os declarados na nota, sem deflação nem conferência com empenho/pagamento.

## Manutenção

Gerado por `rxf publish` a partir da camada gold; `data/publish/manifest.json` traz contagens, sha256 e
data de geração. Reprodução completa: `make pipeline MESES=202504-202509 && make ml && make publish`.
