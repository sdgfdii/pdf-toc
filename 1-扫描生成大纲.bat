@echo off
chcp 65001 >nul
if "%~1"=="" (
  echo Drag a PDF file onto this .bat
  pause
  exit /b
)
python "%~dp0pdf_toc.py" "%~1"
echo.
pause
