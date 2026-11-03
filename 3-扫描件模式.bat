@echo off
chcp 65001 >nul
if "%~1"=="" (
  echo Drag a scanned PDF onto this .bat
  pause
  exit /b
)
python "%~dp0pdf_toc.py" "%~1" --ocr
echo.
pause
