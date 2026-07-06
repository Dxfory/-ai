# 美育AI MCP 项目开发环境激活脚本
# 使用方式: . .\activate.ps1

$python = "C:\Users\wangy\AppData\Local\Programs\Python\Python312\python.exe"
$venv_path = Split-Path -Parent $python
$scripts_path = Join-Path $venv_path "Scripts"

$env:PATH = "$venv_path;$scripts_path;$env:PATH"
$env:PYTHONPATH = "."

Write-Host "美育AI MCP 开发环境已激活" -ForegroundColor Green
Write-Host "  Python:  $python"
Write-Host "  项目目录: $(Get-Location)"
Write-Host ""
Write-Host "  运行服务:  python run_server.py"
Write-Host "  SSE 模式: python run_server.py --sse"
Write-Host "  安装依赖: pip install -r requirements.txt"
