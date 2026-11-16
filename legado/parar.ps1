# =============================================================
# VacinaSegura - encerra os servicos do projeto
# Uso: powershell -ExecutionPolicy Bypass -File parar.ps1
# (o servico padrao do Mosquitto na porta 1883 nao e afetado)
# =============================================================
$portas = @{ 5173 = 'Frontend'; 8000 = 'Backend'; 1884 = 'Mosquitto do projeto'; 8086 = 'InfluxDB' }

foreach ($porta in $portas.Keys) {
    $conexoes = Get-NetTCPConnection -LocalPort $porta -State Listen -ErrorAction SilentlyContinue
    if ($conexoes) {
        $conexoes | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object {
            Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
        }
        Write-Host "Encerrado: $($portas[$porta]) (porta $porta)"
    }
}
Write-Host 'Pronto.'
