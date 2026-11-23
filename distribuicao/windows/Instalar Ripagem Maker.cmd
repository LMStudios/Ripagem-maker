@echo off
chcp 65001 >nul
setlocal
set "RIPAGEM_INSTALL_ROOT=%~dp0"
if not exist "%~dp0instalar.ps1" (
 echo Extraia todo o ZIP antes de executar este arquivo.
 pause
 exit /b 1
)
if not exist "%~dp0Ripagem Maker\Ripagem Maker.exe" (
 echo Os arquivos do aplicativo nao foram encontrados. Extraia todo o ZIP novamente.
 pause
 exit /b 1
)
powershell.exe -NoProfile -STA -Command "try { $ErrorActionPreference='Stop'; $root=$env:RIPAGEM_INSTALL_ROOT; & ([ScriptBlock]::Create([IO.File]::ReadAllText((Join-Path $root 'instalar.ps1')))) -Source (Join-Path $root 'Ripagem Maker') } catch { Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show($_.Exception.Message,'Ripagem Maker'); exit 1 }"
if errorlevel 1 (
 echo A instalacao nao foi concluida. Confira a mensagem exibida.
 pause
 exit /b 1
)
endlocal
