# Copyright 2026 Hailton Santos Reis
# SPDX-License-Identifier: Apache-2.0
# JAAM-AI C2 Windows laboratory: no release promotion or production writes.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$NativeRoot,
    [Parameter(Mandatory=$true)][string]$EvidenceRoot,
    [string]$JavaPath="java",
    [string]$PythonPath="python",
    [string]$CfgPath="",
    [switch]$PreflightOnly,
    [switch]$LaunchGui
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
if ([bool]$PreflightOnly -eq [bool]$LaunchGui) {
    throw "Escolha exatamente -PreflightOnly ou -LaunchGui."
}
function Full([string]$p) { [IO.Path]::GetFullPath($p).TrimEnd('\','/') }
function NoLink([string]$p) {
    $x = Get-Item -LiteralPath $p -Force -ErrorAction Stop
    if (($x.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Link simbolico bloqueado: $p"
    }
}
function Hash([string]$p) { (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant() }
function Exe([string]$name) {
    $c = @(Get-Command -Name $name -CommandType Application -ErrorAction Stop)
    if ($c.Count -lt 1) { throw "Executavel nao encontrado: $name" }
    $p = Full ([string]$c[0].Source)
    if (-not (Test-Path -LiteralPath $p -PathType Leaf)) { throw "Executavel invalido: $p" }
    $p
}
function SaveJson([string]$target, [object]$data) {
    [IO.File]::WriteAllText($target,
        ((ConvertTo-Json -InputObject $data -Depth 12) + [Environment]::NewLine),
        (New-Object Text.UTF8Encoding($false)))
}
function Quote([string]$x) {
    if ($x.Contains('"') -or $x.Contains([char]10) -or $x.Contains([char]13)) {
        throw "Argumento de processo invalido."
    }
    '"' + $x + '"'
}

$root = Full $NativeRoot
$evidence = Full $EvidenceRoot
$comp = [StringComparison]::OrdinalIgnoreCase
$sep = [IO.Path]::DirectorySeparatorChar
if (-not (Test-Path -LiteralPath $root -PathType Container) -or
    [IO.Path]::GetFileName($root) -ne 'JAAM_AI_NATIVE') {
    throw "NativeRoot deve ser a pasta JAAM_AI_NATIVE extraida em laboratorio."
}
if ($evidence.Equals($root,$comp) -or $evidence.StartsWith($root+$sep,$comp)) {
    throw "Nao grave evidencias dentro de JAAM_AI_NATIVE."
}
NoLink $root
$manifestPath = Join-Path $root 'MANIFEST_SHA256.json'
NoLink $manifestPath
$manifestSha = Hash $manifestPath
$m = Get-Content -LiteralPath $manifestPath -Encoding UTF8 -Raw | ConvertFrom-Json
if ($m.package -ne 'JAAM_AI_NATIVE' -or $null -eq $m.files) {
    throw "Manifesto nativo invalido."
}
$entries = @($m.files.PSObject.Properties)
if ($entries.Count -lt 30 -or $entries.Count -gt 5000) {
    throw "Numero inesperado de arquivos no pacote."
}
foreach ($entry in $entries) {
    $name = [string]$entry.Name
    if ($name -notmatch '^[A-Za-z0-9._/-]+$') { throw "Caminho inseguro: $name" }
    $pieces = @($name.Split('/'))
    if (@($pieces | Where-Object { $_ -eq '..' -or $_ -eq '.' -or $_ -eq '' }).Count -gt 0) {
        throw "Travessia de diretorio: $name"
    }
    $target = $root
    foreach ($piece in $pieces) { $target = Join-Path $target $piece; NoLink $target }
    $target = Full $target
    if (-not $target.StartsWith($root+$sep,$comp) -or
        -not (Test-Path -LiteralPath $target -PathType Leaf)) {
        throw "Arquivo do manifesto fora do pacote: $name"
    }
    $expected = [string]$entry.Value.sha256
    if ($expected -notmatch '^[0-9a-f]{64}$' -or
        [long]$entry.Value.bytes -ne (Get-Item -LiteralPath $target).Length -or
        (Hash $target) -ne $expected) {
        throw "Falha SHA-256/tamanho em: $name"
    }
}
$jar = Join-Path $root 'JaamSim2026-03.jar'
$assistant = Join-Path $root 'extensions\academic-assistant'
$corpus = Join-Path $assistant 'examples\c2-preflight\corpus'
$docManifest = Join-Path $assistant 'examples\c2-preflight\manifest.json'
$syntheticCfg = Join-Path $assistant 'examples\jaamsim\c1_fila_simples_referencia.cfg'
foreach ($file in @($jar,$docManifest,$syntheticCfg)) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Falta arquivo de laboratorio: $file" }
}
$java = Exe $JavaPath
$python = Exe $PythonPath
$jver = (& $java --version 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0 -or $jver -notmatch '(?m)^(openjdk|java)\s+25(\.|\s)') {
    throw "Java 25 obrigatorio: $jver"
}
$pver = (& $python -E -s -X utf8 -c "import sys;print('PY_OK',sys.version_info.major,sys.version_info.minor)" 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0 -or $pver -notmatch 'PY_OK\s+3\s+(1[1-9]|[2-9][0-9])') {
    throw "Python 3.11+ obrigatorio: $pver"
}
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [IO.Compression.ZipFile]::OpenRead($jar)
try {
    $names = @{}
    foreach ($x in $zip.Entries) { $names[$x.FullName] = $true }
    foreach ($c in @('com/jaamsim/ui/GUIFrame.class','com/jaamsim/ui/AIAssistantBox.class',
                     'com/jaamsim/ui/C2PreflightPanel.class','com/jaamsim/ui/C2PreflightRunner.class')) {
        if (-not $names.ContainsKey($c)) { throw "Classe do Java ausente: $c" }
    }
}
finally { $zip.Dispose() }

New-Item -ItemType Directory -Path $evidence -Force | Out-Null
$session = Join-Path $evidence ("C2_WINDOWS_LAB_{0}_{1}" -f (Get-Date -Format 'yyyyMMdd_HHmmss'),$PID)
New-Item -ItemType Directory -Path $session -ErrorAction Stop | Out-Null
$outFile = Join-Path $session 'acceptance_report.json'
$report = [ordered]@{
    schema='jaam.ai.c2.windows_acceptance_lab.v1'
    status='PREFLIGHT_ONLY_MANUAL_ACCEPTANCE_PENDING'
    utc=(Get-Date).ToUniversalTime().ToString('o')
    p004='DENY'; full45='NO_GO'; scientific_authorization=$false
    manifest_sha256=$manifestSha; manifest_files_verified=$entries.Count
    jar_sha256=(Hash $jar); java_path=$java; python_path=$python
    cfg_source=$null; cfg_copy=$null
    source_sha_before=$null; source_sha_after=$null
    copy_sha_before=$null; copy_sha_after=$null
    source_cfg_unchanged=$null; copy_cfg_unchanged=$null
    screenshots=@(); manual_gui_accepted=$false
    note='O manifesto e local/autodeclarado, nao uma assinatura. Aceite GUI humano ainda pendente.'
}
SaveJson $outFile $report
Write-Host ("PRECHECK PASS: {0} arquivos, JDK 25, Python >=3.11" -f $entries.Count)
Write-Host "Relatorio: $outFile"
if ($PreflightOnly) { Write-Host 'PREFLIGHT_OK_GUI_WINDOWS_MANUAL_PENDING'; return }

$original = if ($CfgPath -eq '') { $syntheticCfg } else { Full $CfgPath }
if (-not (Test-Path -LiteralPath $original -PathType Leaf) -or
    [IO.Path]::GetExtension($original).ToLowerInvariant() -ne '.cfg') {
    throw "Selecione um CFG valido. Somente uma copia isolada sera carregada."
}
NoLink $original
$lab = Join-Path $session 'laboratorio'
New-Item -ItemType Directory -Path $lab | Out-Null
$cfgCopy = Join-Path $lab 'modelo_laboratorio.cfg'
$before = Hash $original
Copy-Item -LiteralPath $original -Destination $cfgCopy -ErrorAction Stop
if ((Hash $cfgCopy) -ne $before) { throw 'Copia do CFG nao corresponde a origem.' }
$docCopy = Join-Path $lab 'corpus'
Copy-Item -LiteralPath $corpus -Destination $docCopy -Recurse
$manifestCopy = Join-Path $lab 'manifest.json'
Copy-Item -LiteralPath $docManifest -Destination $manifestCopy
$corrupt = Join-Path $lab 'corpus_adulterado'
Copy-Item -LiteralPath $corpus -Destination $corrupt -Recurse
[IO.File]::WriteAllText((Join-Path $corrupt 'guia_sintetico.txt'), 'ALTERACAO SOMENTE NA COPIA',
    (New-Object Text.UTF8Encoding($false)))
$corruptManifest = Join-Path $lab 'manifest_adulterado.json'
Copy-Item -LiteralPath $docManifest -Destination $corruptManifest
$report.cfg_source = $original
$report.cfg_copy = $cfgCopy
$report.source_sha_before = $before
$report.copy_sha_before = Hash $cfgCopy
$report.status = 'GUI_STARTED_MANUAL_REVIEW_PENDING'
SaveJson $outFile $report

Write-Host ''
Write-Host 'LABORATORIO: original e CMD operacional intocados.'
Write-Host 'No JaamSim, abra Ferramentas > Assistente de Simulacao IA > Documentos C2 (previa).'
Write-Host "Corpus sintético (copia): $docCopy"
Write-Host "Manifesto (copia): $manifestCopy"
Write-Host "Corpus adulterado (copia): $corrupt"
Write-Host "Manifesto para teste adversarial: $corruptManifest"
Write-Host 'Use esses caminhos na aba C2, nunca a pasta operacional.'
Write-Host 'ATENCAO: capturas sao opcionais e incluem toda a tela. Feche apps privados.'
$oldRoot = [Environment]::GetEnvironmentVariable('JAAMSIM_ASSISTANT_ROOT','Process')
$oldPython = [Environment]::GetEnvironmentVariable('JAAMSIM_PYTHON','Process')
$process = $null
try {
    [Environment]::SetEnvironmentVariable('JAAMSIM_ASSISTANT_ROOT',$assistant,'Process')
    [Environment]::SetEnvironmentVariable('JAAMSIM_PYTHON',$python,'Process')
    $argsArray = @("-Djaamsim.assistant.root=$assistant","-Djaamsim.python=$python",
                   '-jar',$jar,$cfgCopy)
    $argString = (@($argsArray | ForEach-Object { Quote $_ }) -join ' ')
    $process = Start-Process -FilePath $java -ArgumentList $argString -WorkingDirectory $lab -PassThru
}
finally {
    [Environment]::SetEnvironmentVariable('JAAMSIM_ASSISTANT_ROOT',$oldRoot,'Process')
    [Environment]::SetEnvironmentVariable('JAAMSIM_PYTHON',$oldPython,'Process')
}
try {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    $cases = @(
        @{id='01_citacoes'; text='Busque Queue Server com o corpus autorizado e confira a citacao.'},
        @{id='02_abstencao'; text='Busque xylophonuradazquert: nao deve usar citacoes antigas.'},
        @{id='03_cancelamento'; text='Inicie busca e clique Cancelar. Nenhuma evidencia antiga.'},
        @{id='04_aba'; text='Altere a consulta durante a busca e retorne ao valor original.'},
        @{id='05_adulteracao'; text='Selecione corpus_adulterado e manifesto_adulterado; deve bloquear.'},
        @{id='06_cfg'; text='Confirme que a topologia do modelo nao foi modificada.'}
    )
    foreach ($case in $cases) {
        if ($process.HasExited) { Write-Warning 'Janela encerrada antes dos seis testes.'; break }
        Write-Host ''
        Write-Host $case.text
        $reply = Read-Host ("Digite CAPTURAR para screenshot {0}, ou PULAR" -f $case.id)
        if ($reply -eq 'CAPTURAR') {
            $screen = [Windows.Forms.SystemInformation]::VirtualScreen
            $bitmap = New-Object Drawing.Bitmap($screen.Width,$screen.Height)
            $graphics = [Drawing.Graphics]::FromImage($bitmap)
            $shot = Join-Path $session ($case.id+'.png')
            try {
                $graphics.CopyFromScreen($screen.Left,$screen.Top,0,0,$screen.Size)
                $bitmap.Save($shot,[Drawing.Imaging.ImageFormat]::Png)
            }
            finally { $graphics.Dispose(); $bitmap.Dispose() }
            $report.screenshots += [ordered]@{name=$case.id; file=$shot; sha256=(Hash $shot)}
        }
    }
    Read-Host 'Feche o JaamSim; depois pressione ENTER para fechar a auditoria'
    if (-not $process.HasExited) { $process.WaitForExit() }
    $report.java_exit_code = $process.ExitCode
}
finally {
    $report.source_sha_after = Hash $original
    $report.copy_sha_after = Hash $cfgCopy
    $report.source_cfg_unchanged = $report.source_sha_after -eq $before
    $report.copy_cfg_unchanged = $report.copy_sha_after -eq $report.copy_sha_before
    $report.status = if ($report.source_cfg_unchanged -and $report.copy_cfg_unchanged) {
        'GUI_EXECUTED_MANUAL_REVIEW_REQUIRED'
    } else { 'HOLD_CFG_INTEGRITY_FAILURE' }
    SaveJson $outFile $report
    Write-Host "Relatorio final: $outFile"
    Write-Host "Status: $($report.status). Nenhuma homologacao ou instalacao foi realizada."
}
