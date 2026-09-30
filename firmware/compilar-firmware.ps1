# =============================================================
# VacinaSegura - compila o firmware do ESP32 localmente (Arduino CLI)
# Gera firmware\build\ para a simulacao no Wokwi pelo VS Code,
# sem depender dos servidores de compilacao do site do Wokwi.
# Uso: powershell -ExecutionPolicy Bypass -File firmware\compilar-firmware.ps1
# =============================================================
$ErrorActionPreference = 'Stop'
$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
$aqui = $PSScriptRoot

# O Arduino CLI exige que a pasta tenha o mesmo nome do .ino
$temp = Join-Path $env:TEMP 'vacinasegura-build\sketch'
New-Item -ItemType Directory -Force -Path $temp | Out-Null
Copy-Item "$aqui\sketch.ino" "$temp\sketch.ino" -Force

Write-Host 'Compilando o firmware do ESP32 (a primeira vez demora mais)...'
arduino-cli compile --fqbn esp32:esp32:esp32 --output-dir "$aqui\build" $temp
if ($LASTEXITCODE -ne 0) { Write-Host 'Falha na compilacao.' -ForegroundColor Red; exit 1 }
Write-Host 'Pronto! Agora, no VS Code: F1 > "Wokwi: Start Simulator"' -ForegroundColor Green