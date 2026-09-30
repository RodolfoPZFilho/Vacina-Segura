# =============================================================
# VacinaSegura - configuração inicial do InfluxDB (rodar UMA vez)
# Cria usuário, organização, bucket e token, e gera backend\.env
# Uso: powershell -ExecutionPolicy Bypass -File infra\configurar-influxdb.ps1
# =============================================================
$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $PSScriptRoot
$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')

function Novo-Segredo([int]$tamanho) {
    -join ((48..57) + (65..90) + (97..122) | Get-Random -Count $tamanho | ForEach-Object { [char]$_ })
}

# 1) Garante que o InfluxDB está rodando
if (-not (Get-NetTCPConnection -LocalPort 8086 -State Listen -ErrorAction SilentlyContinue)) {
    Write-Host 'Iniciando o InfluxDB...'
    Start-Process influxd -WindowStyle Hidden
    Start-Sleep -Seconds 6
}

# 2) Setup inicial
$org     = 'vacinasegura'
$bucket  = 'leituras'
$usuario = 'admin'
$senha   = Novo-Segredo 20
$token   = (Novo-Segredo 40) + (Novo-Segredo 40)

influx setup --host http://localhost:8086 --username $usuario --password $senha `
    --org $org --bucket $bucket --token $token --retention 0 --force | Out-Null

# 3) Gera o arquivo backend\.env (NÃO vai para o GitHub)
$envPath = Join-Path $raiz 'backend\.env'
@"
# Gerado por infra\configurar-influxdb.ps1 - NÃO versionar
# Login na interface do InfluxDB (http://localhost:8086): usuario=$usuario senha=$senha
INFLUX_URL=http://localhost:8086
INFLUX_TOKEN=$token
INFLUX_ORG=$org
INFLUX_BUCKET=$bucket

MQTT_HOST=localhost
MQTT_PORT=1884
MQTT_TOPICO=vacinasegura/ubs/+/geladeira/+

TEMP_MIN=2
TEMP_MAX=8
"@ | Set-Content -Path $envPath -Encoding UTF8

Write-Host "InfluxDB configurado. Credenciais salvas em $envPath"
