@echo off
REM Verify environment and write machine-readable artifact (requires PowerShell)
powershell -NoProfile -Command "
$ts=(Get-Date).ToString('yyyyMMddTHHmmss');
$out=Join-Path 'build\\verify_environment' ('verification-windows-'+$ts+'.txt');
New-Item -ItemType Directory -Force -Path (Split-Path $out) | Out-Null;
'' | Out-File -FilePath $out;
('timestamp: '+$ts) | Out-File -FilePath $out -Append;
('OS: '+(Get-CimInstance Win32_OperatingSystem).Caption) | Out-File -FilePath $out -Append;
('OS Version: '+(Get-CimInstance Win32_OperatingSystem).Version) | Out-File -FilePath $out -Append;
try { ('python: '+(python --version 2>&1)) | Out-File -FilePath $out -Append } catch { 'python: not found' | Out-File -FilePath $out -Append }
try { 'pip freeze:' | Out-File -FilePath $out -Append; (python -m pip freeze 2>&1) | Out-File -FilePath $out -Append } catch { 'pip: not found or failed' | Out-File -FilePath $out -Append }
try { ('node: '+(node --version 2>&1)) | Out-File -FilePath $out -Append } catch { 'node: not found' | Out-File -FilePath $out -Append }
try { ('npm: '+(npm --version 2>&1)) | Out-File -FilePath $out -Append } catch { 'npm: not found' | Out-File -FilePath $out -Append }
Write-Output ('Wrote '+$out)
"
exit /b %ERRORLEVEL%
