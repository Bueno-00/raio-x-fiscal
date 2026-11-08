# Raio-X Fiscal: atalhos para rodar tudo por CLI (VPS, sem Docker).
#
#   make install                      cria .venv e instala o pacote em modo editavel
#   make pipeline MESES=202504-202509 download -> bronze -> silver -> quality -> gold -> relatorio
#   make gold                         refaz gold + checagens a partir do que ja esta em silver
#   make ml                           dataset (split temporal) -> treino/avaliacao -> auditoria de NCM
#   make publish                      dataset anonimizado + dataset card (sem publicar nada)
#   make test / make lint             pytest offline / ruff
#
# Produto (tudo local; notas de cliente ficam em entrada-local/, fora do git):
#   make exemplo                      gera as notas sintéticas e o relatório delas em saida-local/exemplo
#   make auditar                      confere entrada-local/ -> saida-local/<data-hora>/relatorio.html + .xlsx
#   make painel                       página local em http://127.0.0.1:8765 (Ctrl+C para parar)
#   make ncm-atualizar                robô da tabela NCM oficial (rodar 1x por dia)

PY      ?= .venv/bin/python
RXF     ?= .venv/bin/rxf
MESES   ?= 202504-202509

.PHONY: exemplo auditar painel ncm-atualizar install pipeline download bronze silver quality gold report ml ml-dataset ml-train ml-audit publish test lint clean-data

install:
	python3 -m venv .venv
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -e ".[dev]"

pipeline:
	$(RXF) pipeline --meses $(MESES)

download bronze silver quality:
	$(RXF) $@ --meses $(MESES)

gold:
	$(RXF) gold

report:
	$(RXF) report

ml: ml-dataset ml-train ml-audit

ml-dataset:
	$(RXF) ml-dataset

ml-train:
	$(RXF) ml-train

ml-audit:
	$(RXF) ml-audit

publish:
	$(RXF) publish

test:
	$(PY) -m pytest

lint:
	.venv/bin/ruff check src tests dags
	.venv/bin/ruff format --check src tests dags

clean-data:
	rm -rf data/bronze data/silver data/gold data/quality data/ml data/publish data/tmp

exemplo:
	$(RXF) exemplos
	$(RXF) auditar exemplos/notas --regras exemplos/regras-do-escritorio.csv --saida saida-local/exemplo
	$(RXF) cadastro exemplos/cadastro-loja-a.csv --saida saida-local/exemplo

auditar:
	@mkdir -p entrada-local
	$(RXF) auditar entrada-local

painel:
	$(RXF) painel

ncm-atualizar:
	$(RXF) ncm-atualizar
