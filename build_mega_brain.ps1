$ErrorActionPreference = "Stop"
python -m pip install --upgrade pyinstaller
python -m PyInstaller --noconfirm --clean --onefile --noconsole --name "MegaBrain" --add-data "frontend;frontend" --add-data "server.py;." mega_brain_launcher.py
Write-Host "Built dist\MegaBrain.exe"
