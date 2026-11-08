# Notas de exemplo dos 8 comércios: o que foi plantado x o que o Raio-X marcou

Gerado por `rxf exemplos-lojas` em 08/11/2026 09:07. Modelo: baseline TF-IDF + SVM hierárquico (fase 1).

8 empresas inventadas (mercado, autopeças, farmácia, material de construção, loja de roupas, restaurante,
papelaria e informática), em 8 estados, com NF-e (modelo 55) e NFC-e (modelo 65) no leiaute 4.00. Os produtos
são descrições reais das notas públicas do Portal da Transparência, com o NCM que aparece em 85% ou mais das
vezes para aquela descrição (`src/raio_x_fiscal/seeds/catalogo_exemplos.csv`, gerado por
`scripts/extrair_catalogo_exemplos.py`). Os erros foram plantados como nascem no escritório: a maioria no
cadastro do produto (e se repete em toda nota com ele), alguns só numa nota.

- 132 notas, 667 itens; 175 itens com algum erro plantado (26%).
- Semáforo: 40 vermelho, 133 amarelo, 494 verde; 6 alertas aceitos pela regra do escritório (um caso certo de propósito).
- **Erros plantados marcados: 184 de 186.**

| Erro plantado | Regra que deve acusar | Itens | Marcados |
|---|---|---:|---:|
| NCM copiado de outro produto no cadastro | `NCM_MODELO` | 40 | 38 |
| NCM antigo, que saiu da tabela oficial | `NCM_INEXISTENTE` | 30 | 30 |
| Código de barras com dígito errado | `GTIN_INVALIDO` | 25 | 25 |
| Empresa do Simples com CST do regime normal | `CST_REGIME` | 19 | 19 |
| NCM diferente digitado só nesta nota | `PRODUTO_NCM_DIVERGENTE` | 4 | 4 |
| CFOP 5.xxx (dentro do estado) numa venda para outro estado | `CFOP_UF` | 33 | 33 |
| Nota cancelada depois (evento na pasta) | `NOTA_CANCELADA` | 14 | 14 |
| CFOP 6.xxx (entre estados) numa venda dentro do estado | `CFOP_UF` | 18 | 18 |
| NCM com 7 dígitos (o Excel comeu o zero da frente) | `NCM_AUSENTE` | 2 | 2 |
| CFOP de compra (1.xxx) numa nota de venda | `CFOP_SENTIDO` | 1 | 1 |

Itens sem erro plantado: 492; sem nenhum alerta: 492.
Cuidado ao ler este número: os produtos limpos foram escolhidos entre descrições em que o modelo concorda
com o NCM de consenso, então ele não mede alarme falso. O alarme falso é medido na amostra pública
([produto_amostra_publica.md](produto_amostra_publica.md)).

## O que passou

- CHA DE CIDREIRA LEAO 25UN com NCM 21069090 (ncm copiado de outro produto no cadastro): semáforo verde.

Nesses casos o NCM errado estava entre os mais prováveis para o modelo, ou o modelo não teve certeza
suficiente; o Raio-X prefere deixar passar a acusar sem certeza.
