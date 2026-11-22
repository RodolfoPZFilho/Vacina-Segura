# Gera o arquivo .env com senhas e chaves aleatorias (ignorado pelo Git).
# Uso:  powershell -ExecutionPolicy Bypass -File gerar-segredos.ps1  [-Forcar]
param([switch]$Forcar)

$raiz = Split-Path -Parent $MyInvocation.MyCommand.Path
$arquivo = Join-Path $raiz '.env'
if ((Test-Path $arquivo) -and -not $Forcar) {
    Write-Host ".env ja existe. Use -Forcar para gerar novos segredos (os volumes antigos deixam de funcionar: rode 'docker compose down -v')." -ForegroundColor Yellow
    exit 0
}

$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
function Novo-Segredo([int]$tamanho = 24) {
    $letras = 'abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    $bytes = New-Object byte[] $tamanho
    $rng.GetBytes($bytes)
    -join ($bytes | ForEach-Object { $letras[$_ % $letras.Length] })
}

$v = [ordered]@{
    'MQTT_SIMULADOR_SENHA'    = Novo-Segredo
    'MQTT_GATEWAY_SENHA'      = Novo-Segredo
    'RABBIT_ADMIN_USUARIO'    = 'vs-admin'
    'RABBIT_ADMIN_SENHA'      = Novo-Segredo
    'RABBIT_GATEWAY_SENHA'    = Novo-Segredo
    'RABBIT_GRAVADOR_SENHA'   = Novo-Segredo
    'RABBIT_INFERENCIA_SENHA' = Novo-Segredo
    'RABBIT_LAB_SENHA'        = Novo-Segredo
    'RABBIT_API_SENHA'        = Novo-Segredo
    'INFLUX_SENHA'            = Novo-Segredo
    'INFLUX_TOKEN'            = Novo-Segredo 48
    'POSTGRES_PASSWORD'       = Novo-Segredo
    'JWT_SEGREDO'             = Novo-Segredo 64
    'ADMIN_SENHA'             = Novo-Segredo 12
    'OPERADOR_SENHA'          = Novo-Segredo 12
    'VISUALIZADOR_SENHA'      = Novo-Segredo 12
    'OLLAMA_MODELO'           = 'llama3.2:3b'
    'TICK_SEGUNDOS'           = '5'
    'PORTA_WEB'               = '8080'
}

$linhas = @('# Gerado por gerar-segredos.ps1 - NAO versionar (esta no .gitignore)')
foreach ($k in $v.Keys) { $linhas += "$k=$($v[$k])" }
# UTF-8 sem BOM (o docker compose nao entende o BOM do PowerShell 5.1)
[System.IO.File]::WriteAllText($arquivo, (($linhas -join "`n") + "`n"), (New-Object System.Text.UTF8Encoding($false)))

Write-Host "Arquivo .env criado." -ForegroundColor Green
Write-Host ""
Write-Host "Usuarios de demonstracao da aplicacao (guarde as senhas):"
Write-Host "  administrador : $($v['ADMIN_SENHA'])"
Write-Host "  operador      : $($v['OPERADOR_SENHA'])"
Write-Host "  visualizador  : $($v['VISUALIZADOR_SENHA'])"
Write-Host ""
Write-Host "Interfaces de estudo (so em 127.0.0.1):"
Write-Host "  InfluxDB  http://127.0.0.1:8086   usuario vacinasegura / $($v['INFLUX_SENHA'])"
Write-Host "  RabbitMQ  http://127.0.0.1:15672  usuario vs-admin / $($v['RABBIT_ADMIN_SENHA'])"
Write-Host "  Adminer   http://127.0.0.1:8081   usuario vacinasegura / $($v['POSTGRES_PASSWORD'])"
Write-Host ""
Write-Host "As senhas ficam no arquivo .env. Proximo passo: docker compose up -d --build"
