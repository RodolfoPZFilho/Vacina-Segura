# =============================================================
# VacinaSegura - inicia todo o projeto com um comando
# Uso: clique com o botao direito > "Executar com o PowerShell"
#      ou: powershell -ExecutionPolicy Bypass -File iniciar.ps1
# =============================================================
$ErrorActionPreference = 'Stop'
$raiz = $PSScriptRoot
$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
$mosquitto = 'C:\Program Files\mosquitto\mosquitto.exe'

function Porta-Ocupada([int]$porta) {
    [bool](Get-NetTCPConnection -LocalPort $porta -State Listen -ErrorAction SilentlyContinue)
}

function Abrir-Janela([string]$titulo, [string]$comando) {
    Start-Process powershell -ArgumentList '-NoExit', '-Command', "`$Host.UI.RawUI.WindowTitle='$titulo'; $comando"
}

# 1) InfluxDB (porta 8086)
if (-not (Porta-Ocupada 8086)) {
    Write-Host '[1/4] Iniciando InfluxDB...'
    Start-Process influxd -WindowStyle Hidden
    Start-Sleep -Seconds 5
} else { Write-Host '[1/4] InfluxDB ja esta rodando.' }

# Primeira execucao: configura o InfluxDB e gera backend\.env
if (-not (Test-Path "$raiz\backend\.env")) {
    Write-Host '      Primeira execucao: configurando o InfluxDB...'
    & "$raiz\infra\configurar-influxdb.ps1"
}

# 2) Mosquitto do projeto (porta 1884, com ponte para o Wokwi)
if (-not (Porta-Ocupada 1884)) {
    Write-Host '[2/4] Iniciando Mosquitto (porta 1884)...'
    Abrir-Janela 'VacinaSegura - Mosquitto' "& '$mosquitto' -c '$raiz\infra\mosquitto.conf' -v"
} else { Write-Host '[2/4] Mosquitto ja esta rodando.' }

# 3) Backend Python (porta 8000)
if (-not (Test-Path "$raiz\backend\.venv")) {
    Write-Host '      Criando ambiente virtual do Python e instalando dependencias...'
    py -3.12 -m venv "$raiz\backend\.venv" 2>$null
    if (-not $?) { python -m venv "$raiz\backend\.venv" }
    & "$raiz\backend\.venv\Scripts\python.exe" -m pip install -r "$raiz\backend\requirements.txt"
}
if (-not (Porta-Ocupada 8000)) {
    Write-Host '[3/4] Iniciando backend Python (porta 8000)...'
    Abrir-Janela 'VacinaSegura - Backend' "cd '$raiz\backend'; .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000"
} else { Write-Host '[3/4] Backend ja esta rodando.' }

# 4) Frontend Vue (porta 5173)
if (-not (Test-Path "$raiz\frontend\node_modules")) {
    Write-Host '      Instalando dependencias do frontend...'
    Push-Location "$raiz\frontend"; npm install; Pop-Location
}
if (-not (Porta-Ocupada 5173)) {
    Write-Host '[4/4] Iniciando frontend (porta 5173)...'
    Abrir-Janela 'VacinaSegura - Frontend' "cd '$raiz\frontend'; `$env:NODE_ENV='development'; npm run dev"
    Start-Sleep -Seconds 4
} else { Write-Host '[4/4] Frontend ja esta rodando.' }

Start-Process 'http://localhost:5173'
Write-Host ''
Write-Host 'Tudo no ar! Dashboard: http://localhost:5173  |  API: http://localhost:8000/docs'
