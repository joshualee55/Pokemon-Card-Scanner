@echo off
REM Run this ONCE. Installs everything the app needs (needs Python from python.org).
cd /d "%~dp0"
python --version >nul 2>&1 || (echo Python is not installed. Get it from https://www.python.org/downloads/ and tick "Add python.exe to PATH" during install. & pause & exit /b 1)
echo Installing... this takes a few minutes.
python -m venv venv || (pause & exit /b 1)
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt || (echo Install failed - see message above. & pause & exit /b 1)
if not exist data\models\clip_vision_q.onnx (
  mkdir data\models 2>nul
  curl -L -o data\models\clip_vision_q.onnx https://huggingface.co/Xenova/clip-vit-base-patch32/resolve/main/onnx/vision_model_quantized.onnx
)
echo.
echo Done! Now double-click start.bat
pause
