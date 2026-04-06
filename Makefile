.PHONY: test test-python test-typescript lint clean

test: test-python test-typescript

test-python:
	@echo "=== Python SDK Tests ==="
	cd python && PYTHONPATH=. python3 -m pytest tests/ -v

test-typescript:
	@echo "=== TypeScript SDK Type Check ==="
	cd typescript && npx tsc --noEmit

lint:
	@echo "=== Python lint ==="
	cd python && python3 -m py_compile oncell/*.py

clean:
	rm -rf python/.venv python/__pycache__ python/.pytest_cache
	rm -rf typescript/node_modules typescript/dist
