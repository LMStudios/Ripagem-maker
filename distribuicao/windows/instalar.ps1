param([Parameter(Mandatory=$true)][string]$Source)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$script:dest=Join-Path $env:LOCALAPPDATA 'Ripagem Maker'
$script:logDir=Join-Path $env:LOCALAPPDATA 'Ripagem Maker Installer'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
function Refresh-Path {
 $env:Path=[Environment]::GetEnvironmentVariable('Path','Machine')+';'+[Environment]::GetEnvironmentVariable('Path','User')+';'+$env:LOCALAPPDATA+'\Microsoft\WinGet\Links;'+$env:Path
}
function Find-Python {
 foreach($base in @('HKCU:\Software\Python\PythonCore\3.12\InstallPath','HKLM:\Software\Python\PythonCore\3.12\InstallPath')) {
  if(Test-Path $base){$p=(Get-ItemProperty $base -ErrorAction SilentlyContinue).ExecutablePath;if($p -and (Test-Path $p)){return $p}}
 }
 return $null
}
function Test-WebView {
 foreach($base in @('HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients','HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients','HKCU:\SOFTWARE\Microsoft\EdgeUpdate\Clients')) {
  foreach($item in @(Get-ChildItem $base -ErrorAction SilentlyContinue)) {
   $v=Get-ItemProperty $item.PSPath -ErrorAction SilentlyContinue
   if($v.name -like '*WebView2*' -and $v.pv -and $v.pv -ne '0.0.0.0'){return $true}
  }
 }
 return $false
}
function Step-Ready($index) {
 Refresh-Path
 switch($index) {
  0 { return [bool](Find-Python) }
  1 { return [bool]((Get-Command ffmpeg -ErrorAction SilentlyContinue) -and (Get-Command ffprobe -ErrorAction SilentlyContinue)) }
  2 { return (Test-WebView) }
  3 { return (Test-Path (Join-Path $dest '.runtime\desktop-instalado-v1')) }
 }
 return $false
}
$form=New-Object Windows.Forms.Form
$form.Text='Instalar Ripagem Maker';$form.ClientSize=New-Object Drawing.Size(760,650);$form.MinimumSize=New-Object Drawing.Size(690,560);$form.StartPosition='CenterScreen';$form.MaximizeBox=$false;$form.AutoScroll=$true;$form.AutoScaleMode='Font';$form.Font=New-Object Drawing.Font('Segoe UI',10);$form.BackColor=[Drawing.Color]::White
try{$form.Icon=New-Object Drawing.Icon((Join-Path $Source 'plataforma\static\assets\app.ico'))}catch{}
$version='';try{$version=(Get-Content -LiteralPath (Join-Path $Source 'VERSION') -Raw).Trim()}catch{}
$accent=[Drawing.ColorTranslator]::FromHtml('#246BFD');$muted=[Drawing.ColorTranslator]::FromHtml('#596579')
function Add-Label($text,$x,$y,$w,$h) { $v=New-Object Windows.Forms.Label;$v.Text=$text;$v.SetBounds($x,$y,$w,$h);$v.ForeColor=$muted;$form.Controls.Add($v);return $v }
$picture=New-Object Windows.Forms.PictureBox;$picture.SetBounds(24,23,48,48);$picture.SizeMode='Zoom';try{$picture.Image=$form.Icon.ToBitmap()}catch{};$form.Controls.Add($picture)
$title=Add-Label 'Ripagem Maker' 86 20 630 34;$title.Font=New-Object Drawing.Font('Segoe UI',21,[Drawing.FontStyle]::Bold);$title.ForeColor=[Drawing.Color]::FromArgb(23,31,45)
$versionLabel=Add-Label ('Instalacao para Windows - versao '+$version) 88 57 630 25
$intro=Add-Label 'Vamos preparar o app neste computador. Componentes ja instalados serao aproveitados. Seus trabalhos e chaves permanecem preservados.' 24 98 712 49
$names=@('Python 3.12','FFmpeg e ffprobe','Microsoft WebView2','Bibliotecas do Ripagem Maker')
$ids=@('Python.Python.3.12','Gyan.FFmpeg','Microsoft.EdgeWebView2Runtime')
$script:states=@()
for($i=0;$i -lt 4;$i++) {
 $name=Add-Label ($names[$i]) 40 (161+$i*32) 400 28
 $state=Add-Label 'Aguardando' 470 (161+$i*32) 250 28;$state.TextAlign='MiddleRight';$script:states+=,$state
}
function Set-Step($index,$text,$ok=$false) { $script:states[$index].Text=$text;$script:states[$index].ForeColor=$(if($ok){[Drawing.Color]::FromArgb(20,120,70)}else{$accent}) }
for($i=0;$i -lt 3;$i++){if(Step-Ready $i){Set-Step $i 'Ja disponivel' $true}}
$destination=Add-Label ('Destino do aplicativo: '+$dest) 24 302 712 45
$agree=New-Object Windows.Forms.CheckBox;$agree.Text='Autorizo instalar os componentes e aceito seus termos de licenca.';$agree.SetBounds(24,350,712,29);$form.Controls.Add($agree)
$link=New-Object Windows.Forms.LinkLabel;$link.Text='Componentes e licencas';$link.SetBounds(24,384,260,25);$form.Controls.Add($link)
$link.Add_LinkClicked({[Windows.Forms.MessageBox]::Show("Python: https://docs.python.org/3/license.html`nFFmpeg (Gyan): https://www.gyan.dev/ffmpeg/builds/`nWebView2: https://developer.microsoft.com/microsoft-edge/webview2/`nBibliotecas: requirements.txt e pywebview (PyPI).`nO WinGet verifica a origem dos pacotes antes da instalacao.",'Componentes')})
$logs=New-Object Windows.Forms.LinkLabel;$logs.Text='Abrir pasta dos registros';$logs.SetBounds(310,384,290,25);$form.Controls.Add($logs);$logs.Add_LinkClicked({Start-Process explorer.exe -ArgumentList ('"'+$logDir+'"')})
$bar=New-Object Windows.Forms.ProgressBar;$bar.SetBounds(24,423,712,12);$bar.Style='Continuous';$bar.Minimum=0;$bar.Maximum=4;$bar.MarqueeAnimationSpeed=28;$form.Controls.Add($bar)
$label=Add-Label 'Tudo pronto para verificar e instalar.' 24 450 712 43;$label.Font=New-Object Drawing.Font('Segoe UI',11,[Drawing.FontStyle]::Bold);$label.ForeColor=[Drawing.Color]::FromArgb(23,31,45)
$elapsed=Add-Label 'A instalacao precisa de internet. O Windows pode solicitar autorizacao.' 24 498 712 25
$errorLabel=Add-Label '' 24 527 712 45;$errorLabel.ForeColor=[Drawing.Color]::FromArgb(180,30,45)
$button=New-Object Windows.Forms.Button;$button.Text='Instalar Ripagem Maker';$button.SetBounds(24,589,360,44);$button.Enabled=$false;$button.BackColor=$accent;$button.ForeColor=[Drawing.Color]::White;$button.FlatStyle='Flat';$button.FlatAppearance.BorderSize=0;$form.Controls.Add($button)
$cancel=New-Object Windows.Forms.Button;$cancel.Text='Fechar';$cancel.SetBounds(404,589,190,44);$form.Controls.Add($cancel)
$details=New-Object Windows.Forms.CheckBox;$details.Appearance='Button';$details.Text='Ver detalhes';$details.TextAlign='MiddleCenter';$details.SetBounds(612,589,124,44);$form.Controls.Add($details)
$detailText=New-Object Windows.Forms.TextBox;$detailText.Multiline=$true;$detailText.ReadOnly=$true;$detailText.ScrollBars='Vertical';$detailText.SetBounds(24,655,712,150);$detailText.Visible=$false;$form.Controls.Add($detailText)
$details.Add_CheckedChanged({$detailText.Visible=$details.Checked;$form.ClientSize=New-Object Drawing.Size(760,$(if($details.Checked){825}else{650}));$details.Text=$(if($details.Checked){'Ocultar detalhes'}else{'Ver detalhes'})})
$agree.Add_CheckedChanged({if(-not $script:running){$button.Enabled=$agree.Checked}})
$script:running=$false;$script:process=$null;$script:step=0;$script:cancelRequested=$false;$script:watch=$null
$timer=New-Object Windows.Forms.Timer;$timer.Interval=650
function Fail-Install($message) {
 $script:running=$false;$timer.Stop();$bar.Style='Continuous';$bar.Value=[Math]::Min($script:step,4);$button.Enabled=$agree.Checked;$button.Text='Tentar novamente';$agree.Enabled=$true;$cancel.Enabled=$true;$cancel.Text='Fechar'
 if($script:step -lt 4){Set-Step $script:step 'Precisa de atencao'}
 $label.Text='Nao foi possivel concluir esta etapa.';$errorLabel.Text=$message;$elapsed.Text='Os componentes concluidos serao aproveitados. Abra os registros para mais detalhes.'
}
function Pause-Install {
 $script:running=$false;$timer.Stop();$bar.Style='Continuous';$bar.Value=[Math]::Min($script:step,4);$button.Text='Continuar instalacao';$button.Enabled=$agree.Checked;$cancel.Enabled=$true;$cancel.Text='Fechar';$agree.Enabled=$true
 $label.Text='Instalacao pausada com seguranca.';$elapsed.Text='A etapa em andamento foi encerrada. Clique em Continuar para aproveitar o que ja esta pronto.'
}
function Next-Step {
 while($script:step -lt 3 -and (Step-Ready $script:step)){Set-Step $script:step 'Ja disponivel' $true;$script:step++}
 if($script:step -eq 4){
  $timer.Stop();$script:running=$false;$bar.Style='Continuous';$bar.Value=4
  $shell=New-Object -ComObject WScript.Shell
  foreach($folder in @([Environment]::GetFolderPath('Desktop'),[Environment]::GetFolderPath('Programs'))){
   $shortcut=$shell.CreateShortcut((Join-Path $folder 'Ripagem Maker.lnk'));$shortcut.TargetPath=Join-Path $dest 'Ripagem Maker.exe';$shortcut.WorkingDirectory=$dest;$shortcut.IconLocation=(Join-Path $dest 'Ripagem Maker.exe')+',0';$shortcut.Save()
  }
  $label.Text='Ripagem Maker instalado. Tudo pronto para comecar.';$elapsed.Text='Atalhos criados na Area de Trabalho e no menu Iniciar.';$errorLabel.Text='';$button.Text='Abrir Ripagem Maker';$button.Enabled=$true;$agree.Visible=$false;$cancel.Text='Concluir';$cancel.Enabled=$true;return
 }
 Set-Step $script:step 'Preparando...';$bar.Style='Marquee';$label.Text='Etapa '+($script:step+1)+' de 4 - '+$names[$script:step];$elapsed.Text='Aguarde. Voce pode acompanhar os detalhes ou parar apos esta etapa.'
 $stdout=Join-Path $logDir ('etapa-'+$script:step+'.log');$stderr=Join-Path $logDir ('etapa-'+$script:step+'-erro.log')
 if($script:step -lt 3){
  $arguments='install --id '+$ids[$script:step]+' --exact --source winget --silent --disable-interactivity --accept-package-agreements --accept-source-agreements'
  $script:process=Start-Process -FilePath $script:winget -ArgumentList $arguments -PassThru -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr
 }else{
  $python=Find-Python
  $script:process=Start-Process -FilePath $python -ArgumentList ('"'+(Join-Path $dest 'prepare_windows.py')+'"') -WorkingDirectory $dest -PassThru -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr
 }
}
$timer.Add_Tick({
 try{
  if($script:process){$script:process.Refresh()}
  if($script:watch){$elapsed.Text='Tempo decorrido: '+$script:watch.Elapsed.ToString('hh\:mm\:ss')+' - '+$(if($script:cancelRequested){'Parando ao concluir a etapa atual.'}else{'Preparando componentes; a janela continua respondendo.'})}
  if($details.Checked){$currentLog=Join-Path $logDir ('etapa-'+$script:step+'.log');$detailText.Text=(@(Get-Content -LiteralPath $currentLog -Tail 10 -ErrorAction SilentlyContinue) -join "`r`n")}
  if($script:process -and $script:process.HasExited){
   $script:process.WaitForExit();$code=$script:process.ExitCode;$script:process=$null
   if($code -ne 0 -and ($script:step -eq 3 -or -not (Step-Ready $script:step))){Fail-Install ('Falha ao preparar '+$names[$script:step]+'. Codigo: '+$code+'. Confira os registros e tente novamente.');return}
   if(-not (Step-Ready $script:step)){Fail-Install ('Nao localizei '+$names[$script:step]+' apos a instalacao. Reinicie o Windows e tente novamente.');return}
   Set-Step $script:step 'Concluido' $true;$script:step++
   if($script:cancelRequested -and $script:step -lt 4){Pause-Install;return}
   Next-Step
  }
 }catch{Fail-Install $_.Exception.Message}
})
$button.Add_Click({
 if($script:step -eq 4){Refresh-Path;Start-Process (Join-Path $dest 'Ripagem Maker.exe');$form.Close();return}
 try{
  $errorLabel.Text='';Refresh-Path;$script:winget=(Get-Command winget -ErrorAction SilentlyContinue).Source
  $needsWinget=@(0..2 | Where-Object {-not (Step-Ready $_)})
  if(-not $script:winget -and $needsWinget.Count){$errorLabel.Text='Instale ou atualize o Instalador de Aplicativo da Microsoft Store e tente novamente.';Start-Process 'ms-windows-store://pdp/?ProductId=9NBLGGH4NNS1';return}
  try{$r=Invoke-RestMethod 'http://127.0.0.1:8765/api/recursos' -TimeoutSec 1}catch{$r=$null}
  if($r.forma_produto){$errorLabel.Text='Feche o Ripagem Maker aberto antes de instalar esta versao.';return}
  if(-not (Test-Path (Join-Path $Source 'app.py')) -or -not (Test-Path (Join-Path $Source 'VERSION'))){throw 'Pacote incompleto. Extraia todo o ZIP ou baixe o instalador novamente.'}
  $button.Enabled=$false;$agree.Enabled=$false;$script:running=$true;$script:cancelRequested=$false;$script:step=0;$cancel.Enabled=$true;$cancel.Text='Parar apos esta etapa';$script:watch=[Diagnostics.Stopwatch]::StartNew();$label.Text='Copiando os arquivos do aplicativo...';$bar.Style='Marquee'
  New-Item -ItemType Directory -Force -Path $dest | Out-Null
  foreach($file in Get-ChildItem -LiteralPath $Source -File -Recurse){
   $relative=$file.FullName.Substring($Source.Length).TrimStart('\');$target=Join-Path $dest $relative
   New-Item -ItemType Directory -Force -Path (Split-Path $target) | Out-Null;Copy-Item -LiteralPath $file.FullName -Destination $target -Force
  }
  $script:process=$null;Next-Step;$timer.Start()
 }catch{Fail-Install $_.Exception.Message}
})
$cancel.Add_Click({if($script:running){$script:cancelRequested=$true;$cancel.Enabled=$false;$label.Text='Parando apos a etapa atual, sem interromper a instalacao de um componente.'}else{$form.Close()}})
$form.Add_FormClosing({param($sender,$event) if($script:running){$event.Cancel=$true;$script:cancelRequested=$true;$cancel.Enabled=$false;$label.Text='A janela sera liberada ao concluir a etapa atual. Os componentes concluidos serao preservados.'}})
[void]$form.ShowDialog()
