# Prueba de carga de FireCal: arranca el servidor de esta copia del repositorio, lo limita a
# N nucleos (para parecerse a una instancia de Cloud Run), simula a las personas y lo apaga.
#
# Uso (desde la raiz del repositorio, con los datos cargados: firecal plan-events):
#   .\auditoria\scripts\carga_escenario.ps1 -Label "60 personas"                       # 60, 1 nucleo
#   .\auditoria\scripts\carga_escenario.ps1 -Label "misma IP" -Modo misma-ip           # una sala
#   .\auditoria\scripts\carga_escenario.ps1 -Label "200" -Users 200 -Cores 2
param([string]$Label = "prueba", [int]$Port = 8040, [int]$Cores = 1, [int]$Users = 60,
      [double]$Ramp = 10, [string]$Modo = "ips-distintas", [string]$App = "api.main:app")
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$backend = Join-Path $root "plataforma_local\backend"
$py = Join-Path $backend ".venv\Scripts\python.exe"
# FIRECAL_TRUST_PROXY=1: el servidor toma la IP de X-Forwarded-For (cada persona simulada trae la suya).
$env:PYTHONUTF8 = "1"; $env:FIRECAL_TRUST_PROXY = "1"; $env:FIRECAL_FRONTEND_DIR = ""
$srv = Start-Process -FilePath $py -WorkingDirectory $backend -PassThru -WindowStyle Hidden `
    -ArgumentList @("-m", "uvicorn", $App, "--host", "127.0.0.1", "--port", "$Port", "--log-level", "warning")
$all = @($srv.Id)
try {
    foreach ($i in 1..60) {
        try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -UseBasicParsing).StatusCode -eq 200) { break } }
        catch { Start-Sleep -Milliseconds 700 }
    }
    # El python del entorno virtual lanza al python real como proceso hijo: se limitan todos.
    $tabla = Get-CimInstance Win32_Process | Select-Object ProcessId, ParentProcessId
    $nuevo = @($srv.Id)
    while ($nuevo.Count) {
        $nuevo = @($tabla | Where-Object { $nuevo -contains $_.ParentProcessId } | ForEach-Object { $_.ProcessId })
        $all += $nuevo
    }
    $mask = [IntPtr]([int]([math]::Pow(2, $Cores) - 1))
    foreach ($id in $all) { try { (Get-Process -Id $id -ErrorAction Stop).ProcessorAffinity = $mask } catch {} }
    $null = Invoke-WebRequest "http://127.0.0.1:$Port/api/metadatos" -UseBasicParsing
    & $py -I -X utf8 -W ignore (Join-Path $PSScriptRoot "carga_usuarios.py") "http://127.0.0.1:$Port" $Users $Ramp $Label $Modo
    $mem = 0; $cpu = 0
    foreach ($id in $all) {
        try { $p = Get-Process -Id $id -ErrorAction Stop; $mem += $p.PeakWorkingSet64; $cpu += $p.TotalProcessorTime.TotalSeconds } catch {}
    }
    "  servidor: {0} nucleo(s) | pico de memoria {1:N0} MB | CPU usada {2:N0} s" -f $Cores, ($mem / 1MB), $cpu
    try { "  limites: " + (Invoke-WebRequest "http://127.0.0.1:$Port/health/limits" -UseBasicParsing).Content } catch {}
}
finally {
    foreach ($id in $all) { try { Stop-Process -Id $id -Force -ErrorAction Stop } catch {} }
}
