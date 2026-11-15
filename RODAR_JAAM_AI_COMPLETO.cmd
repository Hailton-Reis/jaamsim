@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul 2>nul
pushd "%~dp0" >nul 2>nul
if errorlevel 1 (
    echo [ERRO] Pasta principal JAAM-AI inacessivel.
    exit /b 10
)
set "JAAM_ROOT=%CD%"
set "JAAM_JAR=%JAAM_ROOT%\JaamSim2026-03.jar"
if not exist "%JAAM_JAR%" if exist "%JAAM_ROOT%\build\jars\JaamSim2026-03.jar" set "JAAM_JAR=%JAAM_ROOT%\build\jars\JaamSim2026-03.jar"
set "JAAM_REVIEW=%JAAM_ROOT%\extensions\academic-assistant\python\modulo_ia_offline.py"
set "JAAM_OUTPUT=%JAAM_ROOT%\extensions\academic-assistant\output\offline-review"
if not defined JAAM_LEGACY_DIR set "JAAM_LEGACY_DIR=%JAAM_ROOT%\legacy\MC001_v050"
if not defined JAAMSIM_PYTHON set "JAAMSIM_PYTHON=python"
set "JAAMSIM_ASSISTANT_ROOT=%JAAM_ROOT%\extensions\academic-assistant"

rem JAAM-AI main entry point. No inference, tests, or servers start by default.
if "%~1"=="" goto MENU
if /I "%~1"=="--help" goto HELP
if /I "%~1"=="--status" goto CLI_STATUS
if /I "%~1"=="--jaamsim" goto CLI_JAAMSIM
if /I "%~1"=="--review" goto CLI_REVIEW
if /I "%~1"=="--reports" goto CLI_REPORTS
if /I "%~1"=="--mc001" goto CLI_LEGACY
if /I "%~1"=="--build" goto CLI_BUILD
echo [ERRO] Argumento desconhecido: %~1
goto HELP_ERROR

:MENU
cls
echo ==========================================================
echo   JAAM-AI ^| MENU CENTRAL ^| DESENVOLVIMENTO
echo ==========================================================
echo   ENTER ou 1 - Estado do projeto (nao inicia nada)
echo   2          - Abrir JaamSim com Assistente IA e StatFit
echo   3          - Revisar um arquivo CFG, somente offline
echo   4          - Abrir pasta de relatorios
echo   5          - MC-001 v0.50 preservado (modulo opcional)
echo   6          - Compilar JaamSim com Ant (somente fonte)
echo   0          - Sair
echo ----------------------------------------------------------
echo   P004: DENY ^| FULL45: NO-GO ^| Sem inferencia automatica
echo ==========================================================
set "JAAM_OPTION="
set /p "JAAM_OPTION=Opcao: "
if not defined JAAM_OPTION set "JAAM_OPTION=1"
if "%JAAM_OPTION%"=="0" exit /b 0
if "%JAAM_OPTION%"=="1" (
    call :STATUS
    goto MENU_PAUSE
)
if "%JAAM_OPTION%"=="2" (
    call :OPEN_JAAMSIM
    goto MENU_PAUSE
)
if "%JAAM_OPTION%"=="3" (
    set "JAAM_CFG="
    set /p "JAAM_CFG=Caminho completo do arquivo .cfg: "
    call :REVIEW_CFG
    goto MENU_PAUSE
)
if "%JAAM_OPTION%"=="4" (
    call :OPEN_REPORTS
    goto MENU_PAUSE
)
if "%JAAM_OPTION%"=="5" (
    call :OPEN_LEGACY
    goto MENU_PAUSE
)
if "%JAAM_OPTION%"=="6" (
    call :BUILD_JAAMSIM
    goto MENU_PAUSE
)
echo [AVISO] Opcao nao reconhecida.
goto MENU_PAUSE

:MENU_PAUSE
echo.
pause
goto MENU

:CLI_STATUS
call :STATUS
exit /b %ERRORLEVEL%

:CLI_JAAMSIM
call :OPEN_JAAMSIM
exit /b %ERRORLEVEL%

:CLI_REVIEW
if "%~2"=="" (
    echo [ERRO] Informe o arquivo .cfg apos --review.
    exit /b 2
)
set "JAAM_CFG=%~2"
call :REVIEW_CFG
exit /b %ERRORLEVEL%

:CLI_REPORTS
call :OPEN_REPORTS
exit /b %ERRORLEVEL%

:CLI_LEGACY
call :OPEN_LEGACY
exit /b %ERRORLEVEL%

:CLI_BUILD
call :BUILD_JAAMSIM
exit /b %ERRORLEVEL%

:HELP
echo Uso: RODAR_JAAM_AI_COMPLETO.cmd [--status ^| --jaamsim ^| --review "modelo.cfg" ^| --reports ^| --mc001 ^| --build]
echo Sem argumentos: menu interativo, com ENTER seguro em estado somente leitura.
echo MC-001 antigo deve estar intacto na pasta legacy\MC001_v050
echo ou em JAAM_LEGACY_DIR com o CMD original, seu .sha256 e manifesto.
exit /b 0

:HELP_ERROR
echo Execute RODAR_JAAM_AI_COMPLETO.cmd --help para detalhes.
exit /b 2

:STATUS
echo.
echo [JAAM-AI] Estado da candidata (nenhum processo sera iniciado)
if exist "%JAAM_JAR%" (echo   JaamSim Java: DISPONIVEL) else (echo   JaamSim Java: AUSENTE)
if exist "%JAAM_REVIEW%" (echo   Revisao offline Python: DISPONIVEL) else (echo   Revisao offline Python: AUSENTE)
if exist "%JAAM_LEGACY_DIR%\RODAR_JAAM_AI_COMPLETO.cmd" (echo   MC-001 v0.50: PRESENTE - integridade verificada ao abrir) else (echo   MC-001 v0.50: OPCIONAL - nao instalado nesta pasta)
echo   Teste manual GUI: PENDENTE ^| P004: DENY ^| Full45: NO-GO
echo   Dados e relatorios em: "%JAAM_OUTPUT%"
exit /b 0

:OPEN_JAAMSIM
if not exist "%JAAM_JAR%" (
    echo [ERRO] JaamSim2026-03.jar nao encontrado na raiz do pacote.
    exit /b 3
)
where java.exe >nul 2>nul
if errorlevel 1 (
    echo [ERRO] Java nao encontrado no PATH. Requer JDK 25.
    exit /b 4
)
echo [JAAM-AI] Abrindo JaamSim. Esta acao nao inicia Granite nem P004.
java -jar "%JAAM_JAR%"
exit /b %ERRORLEVEL%

:BUILD_JAAMSIM
if not exist "%JAAM_ROOT%\build.xml" (
    echo [INFO] Este pacote nao inclui fontes Java. Compile a partir do checkout GitHub.
    exit /b 7
)
where java.exe >nul 2>nul
if errorlevel 1 (
    echo [ERRO] Java nao encontrado; compilacao exige JDK 25.
    exit /b 4
)
where ant.bat >nul 2>nul
if errorlevel 1 (
    echo [ERRO] Apache Ant nao encontrado no PATH.
    exit /b 4
)
echo [JAAM-AI] Compilacao solicitada explicitamente. Nenhum teste GUI sera iniciado.
call ant -f "%JAAM_ROOT%\build.xml" clean jar
exit /b %ERRORLEVEL%

:REVIEW_CFG
if not exist "%JAAM_REVIEW%" (
    echo [ERRO] Modulo de revisao offline ausente.
    exit /b 5
)
if not defined JAAM_CFG (
    echo [ERRO] Informe o arquivo .cfg a revisar.
    exit /b 2
)
set "JAAM_CFG=%JAAM_CFG:"=%"
if not exist "%JAAM_CFG%" (
    echo [ERRO] CFG nao encontrado: "%JAAM_CFG%"
    exit /b 6
)
echo [JAAM-AI] Revisao offline. O modelo original nao sera modificado.
"%JAAMSIM_PYTHON%" "%JAAM_REVIEW%" "%JAAM_CFG%" --input-type cfg --output-dir "%JAAM_OUTPUT%"
exit /b %ERRORLEVEL%

:OPEN_REPORTS
if not exist "%JAAM_OUTPUT%" (
    echo [INFO] Ainda nao ha pasta de relatorios. Nada a abrir.
    exit /b 0
)
start "" "%JAAM_OUTPUT%"
exit /b %ERRORLEVEL%

:OPEN_LEGACY
rem The historical 2.1 MB self-contained CMD is SHA256 bound to its original
rem filename, sidecar, and release manifest. Never modify/rename it.
set "JAAM_LEGACY_CMD=%JAAM_LEGACY_DIR%\RODAR_JAAM_AI_COMPLETO.cmd"
set "JAAM_LEGACY_SIDE=%JAAM_LEGACY_DIR%\RODAR_JAAM_AI_COMPLETO.cmd.sha256"
set "JAAM_LEGACY_MANIFEST=%JAAM_LEGACY_DIR%\JAAM_AI_LAB_V0_50_RELEASE_MANIFEST.json"
if not exist "%JAAM_LEGACY_CMD%" goto LEGACY_MISSING
if not exist "%JAAM_LEGACY_SIDE%" goto LEGACY_MISSING
if not exist "%JAAM_LEGACY_MANIFEST%" goto LEGACY_MISSING
where powershell.exe >nul 2>nul
if errorlevel 1 (
    echo [BLOQUEADO] PowerShell nao encontrado; nao e seguro abrir MC-001.
    exit /b 8
)
powershell.exe -NoProfile -NonInteractive -Command "$d=$env:JAAM_LEGACY_DIR;$n='RODAR_JAAM_AI_COMPLETO.cmd';$f=Join-Path $d $n;$h=(Get-FileHash -LiteralPath $f -Algorithm SHA256).Hash.ToLowerInvariant();$s=[IO.File]::ReadAllText((Join-Path $d ($n+'.sha256'))).Trim();$m=([IO.File]::ReadAllText((Join-Path $d 'JAAM_AI_LAB_V0_50_RELEASE_MANIFEST.json'))|ConvertFrom-Json);if($h -cne 'ade157d85582a791b6600dc19b611d00535bb58f16b51c3c416c8cd8de5d3931' -or $s -cne ($h+'  '+$n) -or $m.version -cne '0.50' -or $m.central_cmd_sha256 -cne $h -or $m.P004_inference_authorized -ne $false -or $m.Full45_authorized -ne $false -or $m.test_locked -ne $false){exit 9}"
if errorlevel 1 (
    echo [BLOQUEADO] Integridade do MC-001 v0.50 nao confirmada.
    echo   O modulo historico nao foi executado.
    exit /b 9
)
echo [JAAM-AI] Abrindo MC-001 v0.50 ORIGINAL; permanece sujeito a seus proprios bloqueios.
call "%JAAM_LEGACY_CMD%"
exit /b %ERRORLEVEL%

:LEGACY_MISSING
echo [INFO] O modulo MC-001 v0.50 nao faz parte do pacote de desenvolvimento.
echo   Preserve juntos os 3 arquivos originais sem alterar nenhum byte:
echo   RODAR_JAAM_AI_COMPLETO.cmd
echo   RODAR_JAAM_AI_COMPLETO.cmd.sha256
echo   JAAM_AI_LAB_V0_50_RELEASE_MANIFEST.json
echo   Pasta esperada: "%JAAM_LEGACY_DIR%"
echo   Ou defina JAAM_LEGACY_DIR para a pasta original preservada.
exit /b 7
