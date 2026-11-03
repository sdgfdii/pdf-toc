@echo off
chcp 65001 >nul
echo Installing dependencies for pdf-toc ...
echo.
python -m pip install pymupdf rapidocr onnxruntime
echo.
echo Done. Drag a PDF onto 1-扫描生成大纲.bat
pause
