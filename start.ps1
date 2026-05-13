$ErrorActionPreference = "Stop"

if (!(Test-Path ".\.env")) {
    Write-Host "Falta el archivo .env. Copia .env.example a .env y rellena tus tokens reales."
    exit 1
}

if (!(Test-Path ".\.venv")) {
    py -m venv .venv
}

.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Write-Host "Centralita y Oficina Castori arrancando. Deja esta ventana abierta; para apagar, pulsa Ctrl+C."
.\.venv\Scripts\python.exe main.py
