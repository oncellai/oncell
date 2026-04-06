.PHONY: test test-python test-typescript lint clean build

test: test-python test-typescript

test-python:
	@echo "=== Python SDK Tests ==="
	cd python && PYTHONPATH=. .venv/bin/python -m pytest tests/test_client.py -v

test-typescript:
	@echo "=== TypeScript SDK Tests ==="
	cd typescript && npx vitest run

lint:
	@echo "=== Python lint ==="
	cd python && python3 -m py_compile oncell/*.py
	@echo "=== TypeScript type check ==="
	cd typescript && npx tsc --noEmit

build:
	@echo "=== Build TypeScript ==="
	cd typescript && npx tsc

clean:
	rm -rf python/.venv python/__pycache__ python/.pytest_cache
	rm -rf typescript/node_modules typescript/dist
