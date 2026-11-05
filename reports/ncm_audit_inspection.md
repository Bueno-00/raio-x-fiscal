# Inspecao manual da auditoria de NCM

Amostra aleatoria de **60 alertas** (semente fixa) dos 3.580 do mes de teste (2025-09), limiar 0,99.
Cada linha de [ncm_audit.md](ncm_audit.md) foi lida contra a descricao do produto e a nomenclatura
(NCM/SH). Inspecao feita em 04/11/2026 por uma pessoa, sem acesso a nota original: quando a descricao
nao traz o detalhe que decide o codigo, o veredito diz "provavel".

## Resultado

| Veredito | Alertas | % da amostra | Itens (#) |
|---|---:|---:|---|
| Erro de declaracao claro, modelo acerta | 42 | 70% | 1, 2, 5, 6, 9 a 16, 19, 21, 24, 28 a 36, 38 a 41, 43, 44, 47 a 51, 53 a 55, 57 a 60 |
| Erro de declaracao provavel, modelo acerta | 8 | 13% | 3, 4, 25, 26, 27, 37, 42, 56 |
| Livro em codigo vizinho, sem impacto tributario | 5 | 8% | 7, 8, 17, 18, 52 |
| Ambiguo (descricao nao decide) | 1 | 2% | 22 |
| Declarado errado e previsto tambem errado | 1 | 2% | 23 |
| Erro do modelo (declarado correto) | 3 | 5% | 20, 45, 46 |

**Leitura:** 50 de 60 alertas (83%) apontam um NCM declarado errado em que a sugestao do modelo e a
correta; 51 de 60 (85%) tem o declarado errado. So 3 de 60 (5%) sao erro do modelo contra um declarado
correto. Com 60 itens, o intervalo de confianca de 95% para os 83% vai de cerca de 72% a 91%.

## O que os erros reais tem em comum

- **Codigo absurdo de cadastro (troca de capitulo):** cenoura como "cavalos" (#13, #14) e "mostos de uva"
  (#16), abobora como carne bovina (#21), tomate como papel (#9, #10) e como cafe (#43), brocolis como
  cafe (#38), repolho como oleo de milho (#31), biscoito como alho (#53), farinha de trigo como
  desperdicio de algodao (#60), batata palha como carcaca bovina (#44), fluido de freio como prensa
  hidraulica (#51), oleo de motor como freio (#41). Padrao tipico de cadastro de produto errado no ERP do
  fornecedor, repetido em toda nota que ele emite.
- **Codigo generico quando existe o especifico:** "outros produtos horticolas" (07099990) para tomate,
  pimentao e repolho, que tem posicao propria (#1, #2, #12, #28, #29). E o par mais frequente do mes
  inteiro (ver tabela de pares em `ncm_audit.md`).
- **Vizinho errado na mesma posicao:** melao como melancia (#32, #34), couve como couve-flor ou
  couve-de-bruxelas (#57, #58), cebola fresca como cebola seca (#47, #48, #50), feijao preto seco como
  feijao fresco (#59), graos-de-bico como feijao comum (#36), leite condensado como preparacao para
  bebida (#54), trincha como pincel artistico (#55).
- **Provaveis (dependem de detalhe):** paio e salame sao embutidos (1601), nao "outras preparacoes de
  suino" (#3, #4, #25); bacon tem subposicao propria de barriga suina (#26); kit Elecsys de vitamina B12 e
  reagente de diagnostico (3822), nao 3002 (#27); guardanapo provavelmente de papel (#37); retentor
  provavelmente junta de borracha (#42); bolo de chocolate nao e "pao de especiarias" (#56).

## Onde o modelo erra

- **#20 (livro):** previu 4901.10 (folhas soltas) para um livro comum; o declarado 4901.99 esta certo. E o
  par inverso dos livros #7, #8, #17, #18, #52, nos quais o declarado 4901.10 provavelmente esta errado.
  O codigo de livro e confundido nos dois sentidos pelos proprios fornecedores (715 e 334 confusoes no teste).
- **#45, #46 (coxa e sobrecoxa congelada):** previu 0207.12 (frango inteiro, nao cortado) para um pedaco;
  o declarado 0207.14 (pedacos congelados) esta na posicao certa.
- **#23 (ovos de galinha):** o declarado 0407.29 (outras aves) esta errado, mas a sugestao 0407.11 (ovo
  fertilizado para incubacao) tambem; o correto e 0407.21.
- **#22 (abobora):** se a abobora for congelada, o declarado 0710.80 esta certo; a descricao nao diz.

## Ressalvas

- **Impacto tributario varia.** Horticolas e frutas in natura (capitulos 07 e 08, 1.595 dos 3.580 alertas)
  costumam ter tributacao federal zero dos dois lados do erro; ai o problema e de cadastro e estatistica,
  nao de imposto pago. Livros sao imunes. O valor somado dos alertas (R$ 2,63 mi) mede volume, nao imposto.
- **Rotulo e o NCM declarado pelo fornecedor.** A precisao do limiar (92% no mes de validacao) e medida
  contra esse rotulo ruidoso; a inspecao manual mostra que boa parte dos 8% de "erro" sao, na verdade,
  declaracoes erradas.
- **Alguns codigos declarados nao tem nome na tabela NCM usada** (ex.: 08029100, 02071412, 30029000):
  codigos descontinuados ou fora da tabela de referencia. Um proximo passo barato e validar o NCM declarado
  contra a tabela vigente antes do modelo.
- **Amostra pequena (60).** Serve para estimar a ordem de grandeza da precisao dos alertas, nao para
  medir por capitulo.
