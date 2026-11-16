# =============================================================
# VacinaSegura - publica o dashboard na internet (Cloudflare Tunnel)
# Gera um link publico https://....trycloudflare.com que aponta para este PC.
# O link so funciona enquanto esta janela e o sistema (iniciar.ps1) estiverem abertos.
# Cada execucao gera um link NOVO.
# Uso: powershell -ExecutionPolicy Bypass -File publicar-web.ps1
# =============================================================
$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')

if (-not (Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue)) {
    Write-Host 'O dashboard nao esta rodando. Execute iniciar.ps1 primeiro.' -ForegroundColor Yellow
    exit 1
}

Write-Host 'Gerando o link publico (aguarde alguns segundos)...'
Write-Host 'Procure abaixo a linha com https://....trycloudflare.com'
Write-Host 'Para encerrar o acesso publico, feche esta janela ou pressione Ctrl+C.'
Write-Host ''
cloudflared tunnel --no-autoupdate --url http://localhost:5173