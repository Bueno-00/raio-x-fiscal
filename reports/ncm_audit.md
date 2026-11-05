# Auditoria de NCM (mes de teste)

Gerado em 2026-11-05T00:54:09+00:00. Mes 2025-09. Limiar de confianca **0,99**, escolhido no mes de validacao: a meta de 95% nao e alcancavel (o NCM declarado tem ruido), entao vale o limiar de maior precisao medida (92,0%).

## Numeros

- Itens avaliados: **547.718**.
- Predicao diverge do NCM declarado: 124.376 (22,71%). Divergir nao e alerta: a maior parte e incerteza do modelo.
- **Alertas** (divergencia com confianca >= limiar): **3.580** (0,654% dos itens), em 723 descricoes distintas, somando R$ 2.630.873,65.
- Alertas em que o modelo troca o capitulo (2 digitos): 1.305 (troca de capitulo costuma ser erro grosseiro de um dos lados).
- Alertas cuja descricao identica ja aparecia no treino com outro NCM: 3.086 (inconsistencia entre fornecedores).

## Alertas por capitulo declarado (15 maiores)

| Capitulo | Alertas | Valor (R$) |
|---|---:|---:|
| 07 | 1.325 | 642.270,50 |
| 49 | 368 | 110.213,67 |
| 08 | 270 | 184.775,25 |
| 20 | 189 | 95.879,24 |
| 09 | 132 | 38.373,49 |
| 19 | 121 | 202.708,92 |
| 04 | 107 | 160.047,18 |
| 21 | 101 | 276.291,17 |
| 02 | 92 | 140.572,08 |
| 84 | 69 | 52.047,07 |
| 12 | 69 | 70.421,44 |
| 16 | 60 | 51.362,59 |
| 87 | 47 | 82.866,77 |
| 01 | 44 | 50.139,19 |
| 39 | 37 | 10.238,24 |

## Pares declarado -> previsto mais frequentes

| Declarado | Previsto | Alertas | Valor (R$) | Exemplo |
|---|---|---:|---:|---|
| 49011000 Livros, brochuras e impressos semel | 49019900 Outros livros, brochuras e impresso | 329 | 105.312,39 | CONSTRUCAO DO LIVRO PRINCIPIOS DA TECNICA DE EDITO |
| 07041000 Couve-flor e brócolis, frescos ou r | 07049000 Couves, repolho, etc, do gênero Bra | 155 | 39.191,13 | Couve |
| 07099990 Outros produtos hortícolas, frescos | 07049000 Couves, repolho, etc, do gênero Bra | 118 | 33.783,45 | COUVE |
| 07099990 Outros produtos hortícolas, frescos | 07099300 Abóboras, abobrinhas e cabaças, fre | 83 | 40.486,47 | ABOBRINHA |
| 07099990 Outros produtos hortícolas, frescos | 07020000 Tomates, frescos ou refrigerados | 68 | 23.473,57 | TOMATE |
| 07108000 Outros produtos hortícolas congelad | 07096000 Pimentões e pimentas dos gêneros Ca | 63 | 7.670,32 | PIMENTAO VERDE |
| 08071100 Melancias frescas | 08071900 Melões frescos | 53 | 39.541,95 | MELAO |
| 07122000 Cebolas secas, inclusive pedaços, f | 07031019 Cebolas, frescas ou refrigeradas, e | 48 | 7.779,13 | CEBOLA -KG |
| 07099990 Outros produtos hortícolas, frescos | 07070000 Pepinos e pepininhos (cornichons),  | 46 | 9.197,63 | PEPINO |
| 07069000 Beterrabas, rabanetes e outras raíz | 07099990 Outros produtos hortícolas, frescos | 46 | 29.099,79 | HORTIFRUTICOLAS - CARIRU |
| 07099990 Outros produtos hortícolas, frescos | 07096000 Pimentões e pimentas dos gêneros Ca | 40 | 6.138,82 | PIMENTAO |
| 20021000 Tomates inteiros ou pedaços, prepar | 07020000 Tomates, frescos ou refrigerados | 38 | 19.011,98 | TOMATE |
| 12099100 Sementes de produtos hortícolas, pa | 07096000 Pimentões e pimentas dos gêneros Ca | 34 | 3.384,24 | PIMENTAO |
| 07133399 Outros feijões comuns, secos, em gr | 07133319 Outros feijões comuns, pretos, seco | 27 | 206.295,63 | FEIJAO PRETO |
| 07108000 Outros produtos hortícolas congelad | 07099300 Abóboras, abobrinhas e cabaças, fre | 26 | 2.972,04 | ABOBORA |

## Amostra aleatoria para inspecao manual (60 alertas)

Veredito manual em `reports/ncm_audit_inspection.md`.

| # | Descricao | NCM declarado | NCM previsto | Conf. | Valor (R$) |
|---:|---|---|---|---:|---:|
| 1 | TOMATE | 07099990 Outros produtos hortícolas, frescos ou r | 07020000 Tomates, frescos ou refrigerados | 0,999 | 153,00 |
| 2 | TOMATE | 07099990 Outros produtos hortícolas, frescos ou r | 07020000 Tomates, frescos ou refrigerados | 0,999 | 42,60 |
| 3 | LINGUICA PAIO | 16024900 Outras preparações alimentícias e conser | 16010000 Enchidos e produtos semelhantes, de carn | 0,999 | 414,70 |
| 4 | LINGUICA PAIO | 16024900 Outras preparações alimentícias e conser | 16010000 Enchidos e produtos semelhantes, de carn | 0,999 | 208,90 |
| 5 | ABOBRINHA | 08134090 Outras frutas secas | 07099300 Abóboras, abobrinhas e cabaças, fresca o | 0,999 | 45,00 |
| 6 | MELANCIA - KG | 08029100  | 08071100 Melancias frescas | 0,999 | 76,31 |
| 7 | REDES SOCIAIS E ENSINO DE LINGUA; O QUE TEMOS DE APRENDER | 49011000 Livros, brochuras e impressos semelhante | 49019900 Outros livros, brochuras e impressos sem | 0,999 | 212,00 |
| 8 | TRES POEMAS SOBRE O EXTASE,JOHN DONNE, SAN JUAN DE LA CRUZ, RICHARD WA | 49011000 Livros, brochuras e impressos semelhante | 49019900 Outros livros, brochuras e impressos sem | 0,998 | 106,00 |
| 9 | TOMATE IN NATURA | 48022010 Papel e cartão próprios para fabricação  | 07020000 Tomates, frescos ou refrigerados | 0,998 | 100,00 |
| 10 | TOMATE IN NATURA | 48022010 Papel e cartão próprios para fabricação  | 07020000 Tomates, frescos ou refrigerados | 0,998 | 100,00 |
| 11 | PIMENTAO | 12099100 Sementes de produtos hortícolas, para se | 07096000 Pimentões e pimentas dos gêneros Capsicu | 0,998 | 114,72 |
| 12 | PIMENTÃO | 07099990 Outros produtos hortícolas, frescos ou r | 07096000 Pimentões e pimentas dos gêneros Capsicu | 0,998 | 214,83 |
| 13 | CENOURA | 01012900 Cavalos, exceto reprodutores de raça pur | 07061000 Cenouras e nabos, frescos ou refrigerado | 0,998 | 270,00 |
| 14 | CENOURA | 01012900 Cavalos, exceto reprodutores de raça pur | 07061000 Cenouras e nabos, frescos ou refrigerado | 0,998 | 132,90 |
| 15 | CENOURA | 07051900 Outras alfaces frescas ou refrigeradas | 07061000 Cenouras e nabos, frescos ou refrigerado | 0,998 | 119,80 |
| 16 | CENOURA | 22043000 Outros mostos de uvas | 07061000 Cenouras e nabos, frescos ou refrigerado | 0,998 | 147,00 |
| 17 | PEQUENO LIVRO DO TDAH,O | 49011000 Livros, brochuras e impressos semelhante | 49019900 Outros livros, brochuras e impressos sem | 0,997 | 499,00 |
| 18 | A Comunhao das Artes e da Natureza | 49011000 Livros, brochuras e impressos semelhante | 49019900 Outros livros, brochuras e impressos sem | 0,996 | 22,50 |
| 19 | BERINJELA KG | 07019000 Batatas, frescas ou refrigeradas, exceto | 07093000 Berinjelas frescas ou refrigeradas | 0,996 | 23,42 |
| 20 | BRASILIA, A METROPOLE EM CRISE: ENSAIOS SOBRE URBANIZACAO | 49019900 Outros livros, brochuras e impressos sem | 49011000 Livros, brochuras e impressos semelhante | 0,996 | 5,00 |
| 21 | ABOBORA | 02012090 Outras peças não desossadas de bovino, f | 07099300 Abóboras, abobrinhas e cabaças, fresca o | 0,996 | 559,44 |
| 22 | ABOBORA | 07108000 Outros produtos hortícolas congelados, n | 07099300 Abóboras, abobrinhas e cabaças, fresca o | 0,996 | 63,00 |
| 23 | OVOS DE GALINHA BRANCO GRANDE BOM TODO BJ 30 | 04072900 Ovos frescos de outras aves | 04071100 Ovos fertilizados destinados à incubação | 0,996 | 2.248,50 |
| 24 | Aguarras | 39251000 Reservatórios, cisternas, cubas e recipi | 27101230 Aguarrás mineral (white spirit) | 0,995 | 319,14 |
| 25 | SALAME | 02101900 Outras carnes de suíno, salgadas ou em s | 16010000 Enchidos e produtos semelhantes, de carn | 0,995 | 1.900,00 |
| 26 | BACON | 02101900 Outras carnes de suíno, salgadas ou em s | 02101200 Barrigas e peitos, entremeados, de suíno | 0,995 | 167,40 |
| 27 | Vitamin B12 G2 CS Elecsys V2 | 30029000  | 38221990  | 0,995 | 139,69 |
| 28 | REPOLHO | 07099990 Outros produtos hortícolas, frescos ou r | 07049000 Couves, repolho, etc, do gênero Brassica | 0,994 | 116,20 |
| 29 | REPOLHO | 07099990 Outros produtos hortícolas, frescos ou r | 07049000 Couves, repolho, etc, do gênero Brassica | 0,994 | 231,00 |
| 30 | REPOLHO | 07042000 Couve-de-bruxelas, fresca ou refrigerada | 07049000 Couves, repolho, etc, do gênero Brassica | 0,994 | 453,00 |
| 31 | Repolho | 15152990 Outros óleos de milho | 07049000 Couves, repolho, etc, do gênero Brassica | 0,994 | 200,00 |
| 32 | MELAO | 08071100 Melancias frescas | 08071900 Melões frescos | 0,994 | 387,00 |
| 33 | MELAO | 08052100 Mandarinas (incluindo as tangerinas e as | 08071900 Melões frescos | 0,994 | 108,60 |
| 34 | MELAO | 08071100 Melancias frescas | 08071900 Melões frescos | 0,994 | 148,50 |
| 35 | PAPEL T INT. 20X21 BRANCO C 1000 DE VALLI | 39231090 Outros artigos semelhantes a caixas, eng | 48182000 Lenços, incluindo os de desmaquiar, e to | 0,994 | 38,70 |
| 36 | GRAO DE BICO | 07133399 Outros feijões comuns, secos, em grãos | 07132090 Outros grãos-de-bico, secos | 0,994 | 15,98 |
| 37 | GUARDANAPO | 63080000 Sortidos constituídos por cortes de teci | 48183000 Toalhas de mesa e guardanapos, de papel | 0,994 | 5,20 |
| 38 | BROCOLIS | 09011110 Café não torrado, não descafeinado, em g | 07041000 Couve-flor e brócolis, frescos ou refrig | 0,993 | 61,46 |
| 39 | BROCOLIS | 07049000 Couves, repolho, etc, do gênero Brassica | 07041000 Couve-flor e brócolis, frescos ou refrig | 0,993 | 250,50 |
| 40 | CENOURA KG | 07099300 Abóboras, abobrinhas e cabaças, fresca o | 07061000 Cenouras e nabos, frescos ou refrigerado | 0,993 | 125,00 |
| 41 | OLEO MOTOR GASOLINA , ETANOL, FLEX 5W30 ELAION YPF SINTETICO | 87083090 Outros freios e partes, para tratores/ve | 27101932 Óleos lubrificantes com aditivos | 0,993 | 425,00 |
| 42 | RETENTOR | 87089100 Radiadores para tratores e veículos auto | 40169300 Juntas, gaxetas e semelhantes, de borrac | 0,993 | 74,24 |
| 43 | TOMATE CAQUI | 09011110 Café não torrado, não descafeinado, em g | 07020000 Tomates, frescos ou refrigerados | 0,993 | 138,80 |
| 44 | BATATA PALHA | 02011000 Carcaças e meias carcaças de bovino, fre | 20052000 Batatas, preparados ou conservados, exce | 0,993 | 1.089,00 |
| 45 | COXA S/COXA CONG IND AVE NOVA CX20KG | 02071412  | 02071210  | 0,993 | 314,70 |
| 46 | COXA S/COXA CONG IND AVE NOVA CX20KG | 02071412  | 02071210  | 0,993 | 314,70 |
| 47 | CEBOLA -KG | 07122000 Cebolas secas, inclusive pedaços, fatias | 07031019 Cebolas, frescas ou refrigeradas, exceto | 0,993 | 160,00 |
| 48 | CEBOLA KG | 07122000 Cebolas secas, inclusive pedaços, fatias | 07031019 Cebolas, frescas ou refrigeradas, exceto | 0,993 | 199,20 |
| 49 | CEBOLA KG | 07149000 Outras raízes, tubérculos, frescos, etc, | 07031019 Cebolas, frescas ou refrigeradas, exceto | 0,993 | 62,60 |
| 50 | CEBOLA KG | 07122000 Cebolas secas, inclusive pedaços, fatias | 07031019 Cebolas, frescas ou refrigeradas, exceto | 0,993 | 1.020,00 |
| 51 | FLUIDO FREIO DOT 4 BOSCH | 84629119 Outras prensas hidráulicas, de capacidad | 38190000 Fluidos para freios hidráulicos e outros | 0,993 | 280,00 |
| 52 | COISAS QUE TODOS OS PROFESSORES DE PORTUGUES PRECISA SABER | 49011000 Livros, brochuras e impressos semelhante | 49019900 Outros livros, brochuras e impressos sem | 0,992 | 234,00 |
| 53 | BISCOITO MARIA | 07032090 Alhos, frescos ou refrigerados, exceto p | 19053100 Bolachas e biscoitos, adicionados de edu | 0,992 | 600,00 |
| 54 | LEITE CONDENSADO 395 GR | 21069010 Outras preparações para elaboração de be | 04029900 Outros leites, cremes de leite, concentr | 0,992 | 107,46 |
| 55 | TRINCHA 395 2 | 96033000 Pincéis e escovas, para artistas, pincéi | 96034090 Escovas e pincéis para pintar, caiar, en | 0,992 | 44,50 |
| 56 | BOLO DE CHOCOLATE 1K | 19052090 Outros pães de especiarias | 19059090 Outros produtos de padaria, pastelaria,  | 0,991 | 1.318,50 |
| 57 | COUVE | 07042000 Couve-de-bruxelas, fresca ou refrigerada | 07049000 Couves, repolho, etc, do gênero Brassica | 0,991 | 61,95 |
| 58 | COUVE | 07041000 Couve-flor e brócolis, frescos ou refrig | 07049000 Couves, repolho, etc, do gênero Brassica | 0,991 | 607,02 |
| 59 | FEIJAO PRETO 1KG | 07082000 Feijões (vigna, phaseolus spp) frescos o | 07133319 Outros feijões comuns, pretos, secos, em | 0,991 | 850,50 |
| 60 | FARINHA DE TRIGO - SEM FERMENTO | 52021000 Desperdícios de fios de algodão | 11010010 Farinha de trigo | 0,990 | 45,00 |
