# Dataset card: NF-e publicas, descricao de produto -> NCM

Arquivos gerados por `make publish` em `data/publish/` (nao versionados; a FASE 2 publica no Kaggle e
no Hugging Face). Este card acompanha os arquivos.

## Resumo

Itens de notas fiscais eletronicas de compras do governo federal brasileiro, publicados pelo Portal da
Transparencia (CGU), com a **descricao livre do produto** escrita pelo fornecedor e o **NCM de 8
digitos** declarado por ele. Tarefa principal: classificar a descricao no NCM (8 digitos) ou no capitulo
(2 digitos). Tarefas secundarias possiveis: deteccao de inconsistencia de classificacao, normalizacao de
descricoes, estudo de gasto publico por categoria.

- Linhas: **3.094.298** itens (seis meses, 2025-04 a 2025-09), 7.381 NCMs, 96 capitulos,
  ~900 mil descricoes normalizadas distintas.
- Idioma: portugues do Brasil (texto de fornecedor: abreviacoes, maiusculas, erros de digitacao).
- Formatos: Parquet (ZSTD) e CSV gzip, mesmas colunas.

## Fonte e licenca

- Portal da Transparencia, conjunto "Notas Fiscais", download mensal
  (`https://portaldatransparencia.gov.br/download-de-dados/notas-fiscais/AAAAMM`), arquivos
  `NotaFiscal` e `NotaFiscalItem`. Dados abertos do governo federal (catalogo dados.gov.br: ODbL,
  a confirmar na pagina do conjunto no momento da publicacao). Este dataset derivado mantem a mesma
  licenca dos dados de origem; o codigo que o gera e MIT.
- Citacao sugerida: Controladoria-Geral da Uniao, Portal da Transparencia, Notas Fiscais Eletronicas
  (acesso em novembro de 2026); derivado por Rafael Bueno, repositorio `raio-x-fiscal`.

## Privacidade (LGPD)

Removidos: chave de acesso da NF-e (contem o CNPJ do emitente), CPF/CNPJ e razao social do emitente,
inscricao estadual, CNPJ e nome do destinatario, numero e serie da nota. Mantidos: descricao do produto,
NCM e descricao oficial do NCM, CFOP, unidade, quantidade, valores, UF do emitente e do destinatario,
mes e data de emissao. `item_id` e um md5 de (chave de acesso, numero do item), nao reversivel sem a
chave. A descricao do produto e texto livre do fornecedor e pode, em raros casos, conter nomes de marca
ou de pessoas; nenhum filtro adicional foi aplicado alem do que a fonte publica.

## Colunas

| Coluna | Tipo | Descricao |
|---|---|---|
| `item_id` | string | md5(chave_acesso, numero_produto); identificador estavel do item |
| `split` | string | `train` (2025-04 a 2025-07), `valid` (2025-08), `test` (2025-09) |
| `mes_referencia` | string | AAAA-MM do arquivo de origem |
| `descricao_produto` | string | descricao livre do fornecedor, como publicada |
| `descricao_normalizada` | string | minusculas, sem acento, so `[a-z0-9]` separados por espaco |
| `ncm_codigo` | string | NCM de 8 digitos, zero a esquerda restaurado (**rotulo**) |
| `capitulo` | string | 2 primeiros digitos do NCM (rotulo grosso) |
| `posicao` | string | 4 primeiros digitos do NCM |
| `ncm_descricao` | string | descricao oficial do NCM mais frequente para o codigo |
| `cfop` | string | CFOP de 4 digitos (NULL se invalido) |
| `unidade` | string | unidade comercial em maiusculas (`UNIDAD`, `KG`, `PEÇA`, ...) |
| `quantidade` | decimal(18,4) | quantidade do item |
| `valor_unitario` | decimal(18,4) | valor unitario em BRL |
| `valor_total` | decimal(18,2) | valor total do item em BRL |
| `emitente_uf` | string | UF do fornecedor |
| `destinatario_uf` | string | UF do orgao comprador |
| `seen_in_train` | bool | para `valid`/`test`: a `descricao_normalizada` existe no `train` (NULL no treino) |

## Splits e protocolo recomendado

Split **temporal**: treinar em meses anteriores, testar no mais recente. O dataset entrega todos os
itens (com repeticao) para que cada usuario escolha a politica de deduplicacao; a recomendada e a do
baseline:

1. treino colapsado a uma linha por `descricao_normalizada`, rotulo = NCM mais frequente;
2. reportar o teste em quatro cortes: todos os itens, descricoes unicas, itens com
   `seen_in_train = false`, e descricoes unicas nao vistas (numero honesto de generalizacao).

Ruido de rotulo conhecido: 3,6% das descricoes de treino aparecem com mais de um NCM, concentrando 26%
dos itens; entre itens de teste com descricao ja vista, o NCM coincide em 86,5% dos casos. O rotulo e o
que o fornecedor declarou, nao uma verdade auditada.

## Baseline

<!-- CARD_BASELINE_START -->
TF-IDF (palavra 1-2 + caractere 3-5, 400 mil dimensoes) + LinearSVC hierarquico (capitulo, depois NCM
dentro do capitulo), treino 2025-04 a 2025-07, teste 2025-09:

| Corte do teste | Capitulo top-1 / top-5 | NCM top-1 / top-5 | NCM F1 macro |
|---|---:|---:|---:|
| Todos os itens (547.718) | 89,0% / 96,0% | 77,3% / 87,7% | 38,1% |
| Descricoes unicas nao vistas (126.723) | 79,7% / 92,4% | 60,0% / 76,1% | 26,5% |

Detalhes e comparacao com lookup exato e classe majoritaria em `reports/ml_results.md`.
<!-- CARD_BASELINE_END -->

## Limitacoes e vieses

- Cobertura: so compras do governo federal, com forte peso de material medico-hospitalar (capitulo 90),
  medicamentos (30), alimentos (07, 08), livros (49), maquinas e eletronicos (84, 85). Nao representa
  o varejo nem a industria em geral.
- Rotulo ruidoso (acima). Descricoes muito curtas ("VENDA", "SERVICO") sao legitimamente ambiguas.
- Seis meses de um unico ano; sazonalidade e mudancas de tabela NCM nao estao cobertas.
- Valores sao os declarados na nota, sem deflacao nem conferencia com empenho/pagamento.

## Manutencao

Gerado por `rxf publish` a partir da camada gold; `data/publish/manifest.json` traz contagens, sha256 e
data de geracao. Reproducao completa: `make pipeline MESES=202504-202509 && make ml && make publish`.
