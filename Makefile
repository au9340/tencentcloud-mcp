PY ?= python3

.PHONY: test dev package clean

test:
	$(PY) -m unittest discover -s tests -t . -v

dev:
	$(PY) serve.py

# SCF Web 函数：上传这个 zip，启动脚本是 scf_bootstrap
package:
	rm -rf dist
	mkdir -p dist/tencentcloud-mcp
	cp -r main.py serve.py scf_bootstrap mcp_tc dist/tencentcloud-mcp/
	find dist/tencentcloud-mcp -name __pycache__ -type d -exec rm -rf {} +
	chmod +x dist/tencentcloud-mcp/scf_bootstrap
	cd dist/tencentcloud-mcp && zip -qr ../tencentcloud-mcp.zip .
	@echo "done: dist/tencentcloud-mcp.zip"
	@echo "注意：用 Finder/资源管理器重新压缩会丢失 scf_bootstrap 的可执行位"

clean:
	rm -rf dist
	find . -name __pycache__ -type d -exec rm -rf {} +
