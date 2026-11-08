# Raio-X Fiscal: o produto numa amostra real do dado público

Gerado por `rxf avaliar-publico` em 08/11/2026 08:36. Mês 2025-09 (o modelo
foi treinado até 2025-07 e calibrado em 2025-08: este mês ele nunca viu). Notas sorteadas com semente fixa;
cada nota pública passa pelo mesmo motor das notas XML. Sem CST, CRT, GTIN e código do produto no dado
público, as regras que dependem deles não rodam aqui (elas estão cobertas pelos testes e pelos XML de exemplo).

## Semáforo

| | Itens | % |
|---|---:|---:|
| Vermelho (erro provável) | 283 | 0,6% |
| Amarelo (conferir) | 3.003 | 6,0% |
| Verde (ok) | 46.714 | 93,4% |
| **Total** | **50.000** (13.361 notas) | |

Tempo do motor (regras + modelo, CPU de 2 núcleos): 298,1 s, cerca de 168 itens por segundo, medido com o servidor ocupado por outros processos (carga perto de 12 nos 2 núcleos). Em 07/11/2026, com o servidor livre, a mesma amostra rodou a 1.629 itens por segundo.

## Por checagem

| Checagem | Vermelho | Amarelo |
|---|---:|---:|
| NCM não combina com a descrição | 283 | 1.990 |
| CFOP não bate com os estados da nota | 0 | 528 |
| NCM vazio ou fora do formato | 0 | 495 |
| NCM começou a valer depois da data da nota | 0 | 18 |
| NCM não existe na tabela oficial | 0 | 17 |

Além disso, 680 itens com CFOP de dentro do estado numa nota para outro estado
ficaram verdes sozinhos porque a nota diz que a venda foi presencial (nesse caso a operação é interna).

## O modelo e o NCM declarado (sem gabarito humano)

- O NCM da nota é o 1º do modelo em 77,7% dos itens e está entre os 3 primeiros em 86,7%.
- Vermelho do modelo: confiança ≥ 0.99 e o NCM declarado diferente (o limiar da auditoria da fase 1, em que 50 de 60 alertas inspecionados à mão eram erro real).
- Amarelo do modelo: confiança ≥ 0.90 e o NCM declarado fora dos 5 mais prováveis; ou o NCM declarado fora dos 10 mais prováveis e de outro capítulo (confiança ≥ 0.60) ou de outra posição de 4 dígitos (confiança ≥ 0.75). Esta última entrou em 08/11/2026: nesta amostra ela marca mais 1,6% dos itens; em 43% deles quase ninguém usa aquele NCM para aquela descrição no dado público (provável erro real) e em menos de 5% o NCM da nota é o de sempre (provável alarme falso).

| Confiança do 1º NCM do modelo | Itens |
|---|---:|
| ≥ 0,99 | 6.036 |
| 0,90 a 0,99 | 21.126 |
| 0,50 a 0,90 | 13.771 |
| < 0,50 | 9.067 |

## Exemplos de vermelho e amarelo do modelo (os mais confiantes)

| Descrição | NCM da nota | Sugerido | Confiança |
|---|---|---|---:|
| Pontes ( 2 ed ) | 4901.10.00 | 4901.99.00 | 100,0% |
| HORTIFRUTICOLAS - MAXIXE | 0706.90.00 | 0709.99.90 | 100,0% |
| TOMATE | 0901.11.10 | 0702.00.00 | 100,0% |
| BISC DOCE MARIA | 1905.32.00 | 1905.31.00 | 100,0% |
| LINGUICA PAIO | 0203.29.00 | 1601.00.00 | 99,9% |
| IRMAOS VITALE / ARRANJO - METODO PRATICO - VOLUME 1 / Ed: 12022 | 4904.00.00 | 4901.99.00 | 99,9% |
| MELANCIA KG | 0807.19.00 | 0807.11.00 | 99,9% |
| ABOBRINHA * | 0809.40.00 | 0709.93.00 | 99,9% |

## Como ler

- CFOP x estados vira amarelo, nunca vermelho: em compra pública muita venda entre estados sai com
  5.xxx por ser presencial ou por regra da operação. A regra do escritório tira o que é de propósito.
- NCM fora da tabela em nota de 2025 fica amarelo: a cópia mais antiga da tabela guardada é de
  07/11/2026, então para notas anteriores o Raio-X só diz "não existe mais hoje; corrija o cadastro".
