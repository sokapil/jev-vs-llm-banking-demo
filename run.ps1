$ErrorActionPreference = "Stop"
if (-not (Test-Path ".venv")) { py -3.13 -m venv .venv }
& .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if (-not (Test-Path ".env")) {
  Copy-Item .env.example .env
  Write-Host "Created .env. Add TYPESAFE_API_KEY, AZURE_OPENAI_API_KEY, AZURE_OPENAI_BASE_URL and your Azure deployment name, then run .\\run.ps1 again." -ForegroundColor Yellow
  exit 0
}
python app.py
