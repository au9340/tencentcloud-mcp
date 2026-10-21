PY ?= python3

.PHONY: test dev package clean

test:
	$(PY) -m unittest discover -s tests -t . -v

dev:
	$(PY) run_local.py

package:
	rm -rf dist
	mkdir -p dist/tencentcloud-mcp
	cp -r main.py mcp_tc dist/tencentcloud-mcp/
	find dist/tencentcloud-mcp -name __pycache__ -type d -exec rm -rf {} +
	cd dist/tencentcloud-mcp && zip -qr ../tencentcloud-mcp.zip .
	@echo "done: dist/tencentcloud-mcp.zip"

clean:
	rm -rf dist
	find . -name __pycache__ -type d -exec rm -rf {} +
