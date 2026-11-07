# Publicação no Kaggle (FASE 2, modo privado)

Conta: `rafabueno`. Tudo sobe **privado**; virar público é um clique no site (Settings > Visibility) ou `kaggle datasets update` com o metadata ajustado, decisão do dono da conta.

Token: `KAGGLE_API_TOKEN` no `.env` da raiz (modo 600, no .gitignore). Carregar com `set -a; . .env; set +a`. Nunca imprimir.

## 1. Dataset `rafabueno/nfe-ncm-brasil-raio-x-fiscal`

```bash
make publish                                       # gera data/publish/ (parquet, csv.gz, manifest)
.venv/bin/python publicar/kaggle/preparar.py       # copia (hard link) os arquivos + cards para publicar/kaggle/dataset/
.venv/bin/kaggle datasets create -p publicar/kaggle/dataset -t      # 1ª vez (privado por padrão; -t mantém o parquet)
.venv/bin/kaggle datasets version -p publicar/kaggle/dataset -t -m "mensagem"   # versões seguintes
```

Lições da 1ª subida (07/11/2026): o Kaggle **descompacta o `.csv.gz`** (virou `nfe_ncm_dataset.csv` de 731 MB); na próxima versão subir só o Parquet (ou aceitar o CSV grande). Arquivos ocultos da pasta (`.gitignore`) também sobem: por isso o `.gitignore` fica em `publicar/kaggle/`, não em `dataset/`. Título até 50 caracteres, subtítulo de 20 a 80; o título do notebook precisa virar o mesmo slug do `id` (ex.: "Raio-X Fiscal NCM baseline"). Na versão 1 do notebook o parquet não foi achado com `glob("*/...")`; a busca agora é recursiva (`rglob`) e imprime o que existe em `/kaggle/input`.

Varredura de privacidade antes de subir: `publicar/kaggle/varredura.py` (colunas proibidas, CNPJ/CPF, e-mail, caminho de servidor, chave de 44 dígitos). Resultado de 06/11/2026: nenhuma coluna identificadora; nenhum CPF de pessoa; 10 CNPJs de fabricante digitados dentro da descrição livre, mascarados como `[cnpj]` pelo `rxf publish`.

## 2. Notebook `rafabueno/raio-x-fiscal-ncm-baseline`

```bash
.venv/bin/python publicar/kaggle/gerar_notebook.py                 # escreve notebook/raio-x-fiscal-ncm-baseline.ipynb
RXF_PUBLISH_PARQUET=/tmp/amostra.parquet RXF_NB_SMOKE=1 .venv/bin/python publicar/kaggle/gerar_notebook.py --run   # teste de fumaça local
.venv/bin/kaggle kernels push -p publicar/kaggle/notebook           # privado (is_private: true); roda no Kaggle (~10 min em CPU)
.venv/bin/kaggle kernels status rafabueno/raio-x-fiscal-ncm-baseline
```

O notebook é em português com resumo em inglês no fim; modo rápido por padrão (amostra), `MODO_RAPIDO = False` reproduz o protocolo completo.

## 3. Telefone verificado

Sem telefone verificado o Kaggle não libera GPU/TPU nem internet nos notebooks, e pode recusar a criação de dataset pela API. Onde fica: foto do perfil > Settings > seção "Phone verification" > Verify (SMS).
