$ErrorActionPreference = "Stop"
python -m pip install --upgrade faster-whisper
Write-Host "Voice input installed. Download Piper from https://github.com/OHF-Voice/piper1-gpl/releases and download one en_US and one pt_BR voice model."
Write-Host "Set MEGA_BRAIN_PIPER_EN_VOICE and MEGA_BRAIN_PIPER_PT_VOICE to the .onnx model paths before starting Mega Brain."
