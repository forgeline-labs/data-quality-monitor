APP := ./app
SCHEMA := tests/fixtures/ac1_schema.json
CSV := tests/fixtures/ac1.csv

.PHONY: run lint fmt test smoke release

run:
	$(APP) --help

lint:
	ruff check src tests app
	ruff format --check src tests app

fmt:
	ruff format src tests app
	ruff check --fix src tests app

test:
	python3 -m unittest discover -s tests/blackbox -v

smoke:
	@$(APP) validate --schema $(SCHEMA) --json $(CSV) | python3 -c 'import json,sys; data=json.load(sys.stdin); assert data["input"]["lines_valid"] == 3, data; print("smoke: ok")'

release:
	@echo "Release is cut by the maintainer after merge:"
	@echo "  git tag -a v0.1.0 -m 'v0.1.0'"
	@echo "  git push origin v0.1.0"
	@echo "Then create the GitHub Release from CHANGELOG.md."
