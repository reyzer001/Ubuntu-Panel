@echo off
rem ---------------------------------------------------------------
rem Build exe tunggal Windows (tanpa jendela console) dengan alamat
rem server DITANAM di dalamnya - PC klien tinggal dobel-klik.
rem Pakai : build-windows.bat [URL-SERVER]
rem Contoh: build-windows.bat http://192.168.11.126:8000
rem Butuh : pip install pyinstaller
rem ---------------------------------------------------------------
setlocal
cd /d %~dp0

set "SERVER=%~1"
if "%SERVER%"=="" set "SERVER=http://192.168.11.126:8000"

> _build_config.py echo SERVER = "%SERVER%"

python -m PyInstaller --clean --onefile --noconsole --hidden-import=_build_config --name panel-agent panel_agent.py
if errorlevel 1 (
  echo GAGAL - pastikan Python tersedia dan jalankan: python -m pip install pyinstaller
  pause
  exit /b 1
)

echo.
echo Selesai: dist\panel-agent.exe  (1 file ini saja, taruh di PC klien, dobel-klik)
pause
