.PHONY: test lint clean build

test:
	@echo "=== TypeScript SDK Tests ==="
	cd typescript && npx vitest run

lint:
	@echo "=== TypeScript type check ==="
	cd typescript && npx tsc --noEmit

build:
	@echo "=== Build TypeScript ==="
	cd typescript && npx tsc

clean:
	rm -rf typescript/node_modules typescript/dist
