$ErrorActionPreference = "Stop"
python -m pip install --upgrade faster-whisper
python -m pip install --upgrade piper-tts
New-Item -ItemType Directory -Force -Path .\voices | Out-Null
python -m piper.download_voices en_US-lessac-medium --data-dir .\voices
python -m piper.download_voices pt_BR-faber-medium --data-dir .\voices
Write-Host "Local English and Brazilian Portuguese Piper voices are ready."
