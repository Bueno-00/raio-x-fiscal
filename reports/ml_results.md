# Resultados do baseline: descricao -> NCM

Gerado em 2026-11-05T00:52:46+00:00. Treino: 2025-04, 2025-05, 2025-06, 2025-07. Validacao (calibracao): 2025-08. Teste: 2025-09.

## Dados

- Treino: **526.441** descricoes unicas (de 2.062.719 itens), 6.583 NCMs, 96 capitulos.
- Ruido de rotulo no treino: 3,64% das descricoes aparecem com mais de um NCM, e elas concentram 26,02% dos itens (pureza media do rotulo 0,9858).
- Teste: **547.718** itens, 206.928 descricoes unicas; 67,93% dos itens tem descricao identica a alguma do treino e 126.723 descricoes unicas nunca foram vistas.
- Entre os itens vistos, a mesma descricao recebeu o mesmo NCM do treino em 86,52% dos casos (o resto e inconsistencia de classificacao entre fornecedores, nao erro do modelo).

## Tabela principal (mes de teste)

Top-1 / Top-5 / F1 macro / F1 ponderado. `todos` = como em producao (com repeticao); `nao_vistos_unicos` = descricoes nunca vistas, sem repeticao (numero honesto de generalizacao).

### Capitulo (2 digitos)

| Modelo | Subconjunto | n | Top-1 | Top-5 | F1 macro | F1 pond. |
|---|---|---:|---:|---:|---:|---:|
| majoritario | todos | 547.718 | 7,6% | 30,7% | 0,1% | 1,1% |
| majoritario | unicos | 206.928 | 6,1% | 30,4% | 0,1% | 0,7% |
| majoritario | nao_vistos | 175.637 | 5,0% | 30,7% | 0,1% | 0,5% |
| majoritario | nao_vistos_unicos | 126.723 | 5,4% | 27,8% | 0,1% | 0,5% |
| lookup_exato | todos | 547.718 | 65,3% | 73,8% | 56,9% | 70,5% |
| lookup_exato | unicos | 206.928 | 39,8% | 53,7% | 44,6% | 48,5% |
| lookup_exato | nao_vistos | 175.637 | 5,0% | 30,7% | 0,1% | 0,5% |
| lookup_exato | nao_vistos_unicos | 126.723 | 5,4% | 27,8% | 0,1% | 0,5% |
| tfidf_svm_hierarquico | todos | 547.718 | 89,0% | 96,0% | 71,0% | 88,8% |
| tfidf_svm_hierarquico | unicos | 206.928 | 84,7% | 94,6% | 68,2% | 84,5% |
| tfidf_svm_hierarquico | nao_vistos | 175.637 | 80,8% | 92,9% | 60,6% | 80,5% |
| tfidf_svm_hierarquico | nao_vistos_unicos | 126.723 | 79,7% | 92,4% | 60,3% | 79,4% |
| hibrido_lookup_depois_svm | todos | 547.718 | 89,5% | 93,9% | 72,6% | 89,4% |
| hibrido_lookup_depois_svm | unicos | 206.928 | 85,1% | 91,5% | 69,7% | 85,0% |
| hibrido_lookup_depois_svm | nao_vistos | 175.637 | 80,5% | 88,5% | 59,6% | 80,3% |
| hibrido_lookup_depois_svm | nao_vistos_unicos | 126.723 | 79,3% | 87,8% | 59,2% | 79,1% |

### NCM completo (8 digitos)

| Modelo | Subconjunto | n | Top-1 | Top-5 | F1 macro | F1 pond. |
|---|---|---:|---:|---:|---:|---:|
| majoritario | todos | 547.718 | 5,8% | 18,1% | 0,0% | 0,6% |
| majoritario | unicos | 206.928 | 4,5% | 15,9% | 0,0% | 0,4% |
| majoritario | nao_vistos | 175.637 | 3,8% | 16,4% | 0,0% | 0,3% |
| majoritario | nao_vistos_unicos | 126.723 | 4,2% | 13,5% | 0,0% | 0,3% |
| lookup_exato | todos | 547.718 | 60,0% | 64,1% | 33,5% | 63,7% |
| lookup_exato | unicos | 206.928 | 37,0% | 42,8% | 31,3% | 44,9% |
| lookup_exato | nao_vistos | 175.637 | 3,8% | 16,4% | 0,0% | 0,3% |
| lookup_exato | nao_vistos_unicos | 126.723 | 4,2% | 13,5% | 0,0% | 0,3% |
| tfidf_svm_hierarquico | todos | 547.718 | 77,3% | 87,7% | 38,1% | 75,9% |
| tfidf_svm_hierarquico | unicos | 206.928 | 69,8% | 83,2% | 38,0% | 68,2% |
| tfidf_svm_hierarquico | nao_vistos | 175.637 | 62,1% | 77,5% | 26,4% | 59,9% |
| tfidf_svm_hierarquico | nao_vistos_unicos | 126.723 | 60,0% | 76,1% | 26,5% | 57,7% |
| hibrido_lookup_depois_svm | todos | 547.718 | 78,7% | 87,8% | 41,2% | 77,6% |
| hibrido_lookup_depois_svm | unicos | 206.928 | 71,2% | 83,2% | 41,1% | 69,8% |
| hibrido_lookup_depois_svm | nao_vistos | 175.637 | 62,1% | 77,5% | 26,4% | 59,9% |
| hibrido_lookup_depois_svm | nao_vistos_unicos | 126.723 | 60,0% | 76,1% | 26,5% | 57,7% |

## Modelo e custo

- Features: TF-IDF palavra (1-2 gramas, 150.000 termos) + caractere (3-5, 250.000 termos) = 400.000 dimensoes, float32, 46.703.758 valores nao nulos em 526.441 linhas; ajuste em 76,0 s.
- Modelo: LinearSVC um-contra-todos do capitulo (96 classes, 38.400.000 coeficientes densos float32) + 95 LinearSVC por capitulo (6.583 NCMs; 1 capitulo(s) com um unico NCM). Pesos dos sub-modelos podados para esparso: 4,42% dos coeficientes retidos, 13.637.922 no total, concordancia top-1 com o modelo denso nas descricoes de treino = 0,9961.
- Tempo de treino (CPU, 1 nucleo): capitulo 27,8 min, NCM 14,7 min.
- Calibracao por temperatura no mes de validacao: T_capitulo = 0,288, T_ncm = 0,248.
- Latencia de inferencia ponta a ponta (texto normalizado -> top-5, CPU, 2 nucleos): item unico p50 314,0 ms, p95 507,5 ms; em lote de 2.000: 0,312 ms/item. Mes de teste inteiro previsto em 90,8 s.
- Artefatos em `models/` (232 MB, fora do git).

## Calibracao (mes de validacao) e limiar da auditoria

Acuracia do top-1 por faixa de confianca P(ncm) e precisao acumulada acima de cada faixa. Meta da auditoria: precisao >= 95% no mes de validacao.

A meta nao e alcancavel nestes dados: precisao aqui e concordancia com o NCM declarado, e o declarado tem ruido (descricoes identicas recebem NCMs diferentes de fornecedores diferentes). Limiar escolhido: **0,99**, o de maior precisao com pelo menos 1.000 itens acima (45.234 itens, precisao 92,0%).

| Faixa | n | Acuracia na faixa | n acima | Precisao acima |
|---|---:|---:|---:|---:|
| [0,00; 0,20) | 38.192 | 0,3177 | 483.861 | 0,7833 |
| [0,20; 0,40) | 33.512 | 0,4993 | 445.669 | 0,8232 |
| [0,40; 0,50) | 17.105 | 0,5993 | 412.157 | 0,8496 |
| [0,50; 0,60) | 18.711 | 0,6391 | 395.052 | 0,8604 |
| [0,60; 0,70) | 22.102 | 0,7217 | 376.341 | 0,8714 |
| [0,70; 0,80) | 32.910 | 0,7560 | 354.239 | 0,8808 |
| [0,80; 0,90) | 65.081 | 0,8469 | 321.329 | 0,8935 |
| [0,90; 0,95) | 78.446 | 0,8960 | 256.248 | 0,9054 |
| [0,95; 0,99) | 132.568 | 0,9058 | 177.802 | 0,9095 |
| [0,99; 1,01) | 45.234 | 0,9204 | 45.234 | 0,9204 |

## Por capitulo (descricoes nao vistas, unicas; 20 maiores)

| Capitulo | Descricao | Precisao | Recall | F1 | Suporte |
|---|---|---:|---:|---:|---:|
| 90 | Instrumentos e aparelhos de óptica, de fotografia, de cinema | 0,879 | 0,906 | 0,892 | 17.188 |
| 84 | Reatores nucleares, caldeiras, máquinas, aparelhos e instrum | 0,762 | 0,794 | 0,778 | 13.331 |
| 85 | Máquinas, aparelhos e materiais elétricos, e suas partes; ap | 0,815 | 0,855 | 0,835 | 12.368 |
| 39 | Plásticos e suas obras | 0,751 | 0,773 | 0,762 | 9.604 |
| 87 | Veículos automóveis, tratores, ciclos e outros veículos terr | 0,680 | 0,695 | 0,688 | 6.976 |
| 49 | Livros, jornais, gravuras e outros produtos das indústrias g | 0,921 | 0,948 | 0,934 | 6.788 |
| 73 | Obras de ferro fundido, ferro ou aço | 0,716 | 0,691 | 0,703 | 4.834 |
| 30 | Produtos farmacêuticos | 0,869 | 0,890 | 0,879 | 4.765 |
| 38 | Produtos diversos das indústrias químicas | 0,803 | 0,797 | 0,800 | 4.325 |
| 40 | Borracha e suas obras | 0,709 | 0,706 | 0,708 | 3.477 |
| 82 | Ferramentas, artigos de cutelaria e talheres, e suas partes, | 0,812 | 0,817 | 0,814 | 3.026 |
| 32 | Extratos tanantes e tintoriais; taninos e seus derivados; pi | 0,860 | 0,839 | 0,849 | 2.738 |
| 96 | Obras diversas | 0,821 | 0,848 | 0,834 | 2.168 |
| 48 | Papel e cartão; obras de pasta de celulose, de papel ou de c | 0,799 | 0,797 | 0,798 | 1.979 |
| 27 | Combustíveis minerais, óleos minerais e produtos da sua dest | 0,826 | 0,861 | 0,843 | 1.664 |
| 19 | Preparações à base de cereais, farinhas, amidos, féculas ou  | 0,863 | 0,869 | 0,866 | 1.484 |
| 94 | Móveis; mobiliário médico-cirúrgico; colchões, almofadas e s | 0,782 | 0,777 | 0,780 | 1.483 |
| 83 | Obras diversas de metais comuns | 0,691 | 0,677 | 0,684 | 1.402 |
| 34 | Sabões, agentes orgânicos de superfície, preparações para la | 0,768 | 0,769 | 0,769 | 1.275 |
| 70 | Vidro e suas obras | 0,837 | 0,782 | 0,809 | 1.197 |

## Capitulos mais confundidos (verdadeiro -> previsto)

| Verdadeiro | Previsto | n |
|---|---|---:|
| 87 Veículos automóveis, tratores, ciclos e  | 84 Reatores nucleares, caldeiras, máquinas, | 698 |
| 84 Reatores nucleares, caldeiras, máquinas, | 87 Veículos automóveis, tratores, ciclos e  | 588 |
| 84 Reatores nucleares, caldeiras, máquinas, | 85 Máquinas, aparelhos e materiais elétrico | 582 |
| 85 Máquinas, aparelhos e materiais elétrico | 84 Reatores nucleares, caldeiras, máquinas, | 574 |
| 40 Borracha e suas obras | 87 Veículos automóveis, tratores, ciclos e  | 414 |
| 87 Veículos automóveis, tratores, ciclos e  | 85 Máquinas, aparelhos e materiais elétrico | 354 |
| 39 Plásticos e suas obras | 84 Reatores nucleares, caldeiras, máquinas, | 343 |
| 85 Máquinas, aparelhos e materiais elétrico | 90 Instrumentos e aparelhos de óptica, de f | 340 |
| 87 Veículos automóveis, tratores, ciclos e  | 40 Borracha e suas obras | 336 |
| 84 Reatores nucleares, caldeiras, máquinas, | 39 Plásticos e suas obras | 329 |
| 90 Instrumentos e aparelhos de óptica, de f | 85 Máquinas, aparelhos e materiais elétrico | 323 |
| 90 Instrumentos e aparelhos de óptica, de f | 84 Reatores nucleares, caldeiras, máquinas, | 316 |

## NCMs mais confundidos (verdadeiro -> previsto)

| Verdadeiro | Previsto | n |
|---|---|---:|
| 49011000 Livros, brochuras e impressos semelhantes, em | 49019900 Outros livros, brochuras e impressos semelhan | 715 |
| 49019900 Outros livros, brochuras e impressos semelhan | 49011000 Livros, brochuras e impressos semelhantes, em | 334 |
| 87089990 Outras partes e acessórios para tratores e ve | 87088000 Amortecedores de suspensão para tratores e ve | 186 |
| 39172300 Tubo rígido, de polímeros de cloreto de vinil | 39174090 Outros acessórios para tubos, de plásticos | 141 |
| 84219999 Outras partes de aparelhos para filtrar ou de | 84212300 Aparelhos para filtrar óleos minerais nos mot | 133 |
| 87088000 Amortecedores de suspensão para tratores e ve | 87089990 Outras partes e acessórios para tratores e ve | 128 |
| 84212990 Outros aparelhos para filtrar ou depurar líqu | 84212300 Aparelhos para filtrar óleos minerais nos mot | 106 |
| 32081010 Tintas de poliésteres, dispersos/dissolv.meio | 32091010 Tintas de polímeros acrílicos/vinílicos, disp | 102 |
| 38229000  | 38221990  | 100 |
| 84212300 Aparelhos para filtrar óleos minerais nos mot | 84219999 Outras partes de aparelhos para filtrar ou de | 96 |
| 40169990 Outras obras de borracha vulcanizada, não end | 87089990 Outras partes e acessórios para tratores e ve | 95 |
| 90184999 Outros instrumentos e aparelhos para odontolo | 90189099 Outros instrumentos e aparelhos para medicina | 87 |

## Exemplos de erro (descricoes nao vistas, ordenados por confianca)

| Descricao | NCM declarado | NCM previsto | Conf. | Declarado no top-5 | Mesmo cap. |
|---|---|---|---:|---|---|
| TE REDUCAO SOLDAVEL 50X32MM | 73071990 Outros acessórios para tubos moldados de | 39174090 Outros acessórios para tubos, de plástic | 0,986 | nao | nao |
| CHUMBADOR CBA 1/4 X 3 C/PARAF | 73181500 Outros parafusos e pinos ou pernos, mesm | 73181900 Outros artefatos roscados, de ferro fund | 0,923 | sim | sim |
| Verniz automotivo PU | 38140090 Outros solventes e diluentes orgânicos c | 32089010 Tintas de outros polímeros sintéticos, e | 0,910 | nao | nao |
| FITA ADESIVA MATERIAL CREPE COR BRANCA | 39172300 Tubo rígido, de polímeros de cloreto de  | 48114110 Papel e cartão auto-adesivos, em tiras o | 0,898 | nao | nao |
| Z-JILO - COOPGRANDE | 07051900 Outras alfaces frescas ou refrigeradas | 07099990 Outros produtos hortícolas, frescos ou r | 0,873 | sim | sim |
| BORDADO EM CAMISA MILITAR GRADUACAO SD NOME DE GUERRA MILITAR | 49119100 Estampas, gravuras e fotografias | 58109100 Bordados de algodão, em peça, em tiras o | 0,818 | nao | nao |
| Carne bovina sem osso in natura tipo alcatra, peca inteira | 02022090 Outras peças não desossadas de bovino, c | 02102000 Carnes de bovinos, salgadas/em salmoura/ | 0,771 | nao | sim |
| GORDURA CONG | 02062990 Outras miudezas comestíveis de bovino, c | 02071419  | 0,716 | nao | sim |
| CARBONO PARA ARTICULAR USO ODONTOLOGICO MATERIAL: EM PAPEL, FORMATO: F | 30064012 Outros produtos para obturação dentária | 48116090 Outros papéis e cartões revestidos, impr | 0,694 | nao | nao |
| FORRO PARA BANDEJA LINHO | 65070000 Carneiras, forros, capas, armações, pala | 82159910 Colheres, garfos, conchas, escumadeiras, | 0,570 | nao | nao |
| FILTRO COMBUSTIVEL - PSC995 | 84212300 Aparelhos para filtrar óleos minerais no | 84212990 Outros aparelhos para filtrar ou depurar | 0,431 | sim | sim |
| BUCHA BRACO OSCILANTE DIANT | 40169990 Outras obras de borracha vulcanizada, nã | 87088000 Amortecedores de suspensão para tratores | 0,357 | sim | nao |
| Oring Protec 20/14 - (20 unid) | 84819090 Partes de torneiras, outros dispositivos | 34029039 Outras preparações para lavagem (deterge | 0,346 | nao | nao |
| BALDE CONCRETO PT | 39249000 Outros artigos de higiene ou de toucador | 39269090 Outras obras de plásticos | 0,314 | sim | sim |
| CAMERA FOTOGRAFICA SONY FX30 | 85258921  | 85258929  | 0,280 | nao | sim |
| FITA ISOLANTE ELETRICA AUTOFUSAO 19X10MTS 69KV | 40059190 Outras borrachas misturadas, não vulcani | 59061000 Fitas adesivas de largura não superior a | 0,261 | sim | nao |
| CAIXA ORGANIZADORA COM TAMPA 29 L | 39249000 Outros artigos de higiene ou de toucador | 95030039 Outros brinquedos que representem animai | 0,250 | sim | nao |
| BUCHA ISOLAMENTO DIANT ESQ | 40169990 Outras obras de borracha vulcanizada, nã | 87089990 Outras partes e acessórios para tratores | 0,244 | sim | nao |
| Cinto tatico modular com protetor de lombar na cor preta para transpor | 62171000 Outros acessórios confeccionados de vest | 42033000 Cintos, cinturões e bandoleiras ou talab | 0,211 | nao | nao |
| ALICATE MODELO CAPRI PARA ABERTURA DE ANILHAS ( DIAMETRO 1,8MM ATE 30, | 82032010 Alicates (mesmo cortantes) | 90189099 Outros instrumentos e aparelhos para med | 0,176 | nao | nao |
| JUNTA BOMBA VACUO AMAROK 2.0 | 73269090 Outras obras de ferro ou aço | 84141000 Bombas de vácuo | 0,094 | nao | nao |
| GARFO 23CM | 82079000 Outras ferramentas intercambiáveis, de m | 73269090 Outras obras de ferro ou aço | 0,073 | nao | nao |
| TETO DIANTEIRO | 87082999 Outras partes e acessórios de carroceria | 87089990 Outras partes e acessórios para tratores | 0,015 | sim | sim |
| LANT.TETO VW DELIVERY/WORKER | 85122021 Luzes fixas para automóveis e outros cic | 85122022 Luzes indicadoras de manobras, dos tipos | 0,014 | nao | sim |
| HP 3R9E1AV MGI Cable lock MiniPH4mm DIB | 83011000 Cadeados de metais comuns | 90211020 Artigos e aparelhos para fraturas | 0,009 | nao | nao |
