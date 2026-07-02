PY := .venv/bin/python

.PHONY: setup refresh web dev build

setup:
	python3 -m venv .venv
	.venv/bin/pip install -e "pipeline[thesis]"
	cd web && npm install

refresh:
	cd pipeline && ../$(PY) -m buffet.refresh

dev:
	cd web && npm run dev

build:
	cd web && npm run build
