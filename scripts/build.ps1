param(
    [switch]$NoClean
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$buildXml = Join-Path $repoRoot "build.xml"

function Invoke-CheckedCommand {
    param(
        [string]$Command,
        [string[]]$Arguments
    )

    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Command failed with exit code $LASTEXITCODE"
    }
}

if (-not (Get-Command java -ErrorAction SilentlyContinue)) {
    throw "Java was not found. Install JDK 25 and set JAVA_HOME."
}
if (-not (Get-Command ant -ErrorAction SilentlyContinue)) {
    throw "Apache Ant was not found. Install Ant 1.10+ and set ANT_HOME."
}

$targets = if ($NoClean) { @("jar") } else { @("clean", "jar") }
Invoke-CheckedCommand -Command "ant" -Arguments (@("-f", $buildXml) + $targets)

$jarPath = Join-Path $repoRoot "build\jars\JaamSim2026-03.jar"
if (-not (Test-Path -LiteralPath $jarPath)) {
    throw "Expected JAR was not generated: $jarPath"
}

$entries = & jar tf $jarPath
if ($LASTEXITCODE -ne 0) {
    throw "Unable to inspect generated JAR."
}
foreach ($required in @(
    "com/jaamsim/ui/AIAssistantBox.class",
    "com/jaamsim/ui/StatFitAssistantBox.class"
)) {
    if ($entries -notcontains $required) {
        throw "Required class was not found in JAR: $required"
    }
}

Write-Output "BUILD_OK $jarPath"

