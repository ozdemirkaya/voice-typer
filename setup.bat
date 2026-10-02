@echo off
chcp 65001 >nul
echo.
echo ╔══════════════════════════════════════╗
echo ║      Voice Typer — Kurulum           ║
echo ╚══════════════════════════════════════╝
echo.

REM Python kontrolü
python --version >nul 2>&1
if errorlevel 1 (
    echo [HATA] Python bulunamadi.
    echo        https://python.org adresinden Python 3.11+ indirin.
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version') do set PYVER=%%v
echo [OK] Python %PYVER% bulundu.

REM Sanal ortam kontrolü
if not exist ".venv\" (
    echo [*] Sanal ortam olusturuluyor...
    python -m venv .venv
    if errorlevel 1 (
        echo [HATA] Sanal ortam olusturulamadi.
        pause
        exit /b 1
    )
    echo [OK] Sanal ortam olusturuldu.
) else (
    echo [OK] Sanal ortam mevcut.
)

REM Bağımlılıkları yükle — YALNIZCA .venv içindeki pip kullanılır
echo [*] Bagimliliklar yukleniyor... (ilk kurulumda zaman alabilir)
.venv\Scripts\python.exe -m pip install --upgrade pip -q
.venv\Scripts\python.exe -m pip install -r requirements.txt

if errorlevel 1 (
    echo [HATA] Bagimlilik yuklemesi basarisiz.
    pause
    exit /b 1
)

echo.
echo ╔══════════════════════════════════════╗
echo ║   Kurulum tamamlandi!                ║
echo ║   Baslatmak icin: run.bat            ║
echo ╚══════════════════════════════════════╝
echo.
pause
