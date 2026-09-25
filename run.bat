@echo off
if not exist .venv py -3.13 -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if not exist .env (
  copy .env.example .env >nul
  echo Created .env. Add TYPESAFE_API_KEY, AZURE_OPENAI_API_KEY, AZURE_OPENAI_BASE_URL and your Azure deployment name, then run run.bat again.
  pause
  exit /b 0
)
python app.py
