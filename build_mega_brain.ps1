$ErrorActionPreference = "Stop"
python -m pip install --upgrade pyinstaller
python -m PyInstaller --noconfirm --clean --onefile --console --name "MegaBrain" --add-data "frontend;frontend" mega_brain_launcher.py
Write-Host "Built dist\MegaBrain.exe"
