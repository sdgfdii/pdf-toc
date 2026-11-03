@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [1/4] Cleaning previous build ...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [2/4] Building ...
python -m PyInstaller --noconfirm --onedir --console --name pdf-toc ^
  --collect-all rapidocr --collect-all omegaconf ^
  --exclude-module pymupdf.layout ^
  --exclude-module tkinter --exclude-module matplotlib ^
  --exclude-module scipy --exclude-module pandas ^
  --exclude-module PyQt5 --exclude-module IPython ^
  pdf_toc.py
if errorlevel 1 goto fail

echo [3/4] Dropping ffmpeg dll (ocr does not need video io) ...
if exist dist\pdf-toc\_internal\cv2\opencv_videoio_ffmpeg*_64.dll del /q dist\pdf-toc\_internal\cv2\opencv_videoio_ffmpeg*_64.dll

echo [4/4] Packaging zip ...
if exist dist\pdf-toc-win64.zip del /q dist\pdf-toc-win64.zip
powershell -NoProfile -Command "Compress-Archive -Path 'dist\pdf-toc' -DestinationPath 'dist\pdf-toc-win64.zip' -CompressionLevel Optimal"

echo.
echo Done: dist\pdf-toc\pdf-toc.exe
pause
exit /b 0

:fail
echo.
echo Build failed.
pause
exit /b 1
