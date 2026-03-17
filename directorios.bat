@echo off
setlocal

REM === Carpeta raíz del proyecto ===
set PROJ=hospedaje

REM === Crear estructura de carpetas ===
mkdir  2>nul
mkdir "core" 2>nul
mkdir "ui" 2>nul
mkdir "data" 2>nul

REM === Crear archivos vacíos ===
type nul > "app.py"
type nul > "schema.sql"
type nul > "requirements.txt"

type nul > "core\__init__.py"
type nul > "core\db.py"
type nul > "core\models.py"
type nul > "core\repositories.py"
type nul > "core\utils.py"

type nul > "ui\__init__.py"
type nul > "ui\admin.py"
type nul > "ui\catalogos.py"
type nul > "ui\reservas.py"
type nul > "ui\reportes.py"

echo.
echo ✅ Estructura creada en: %PROJ%
echo    Ahora abre la carpeta en VS Code y pega el contenido de cada archivo.
echo.
echo Pasos de ejecución:
echo    1) cd %PROJ%
echo    2) py -3.11 -m venv .venv
echo    3) .\.venv\Scripts\activate
echo    4) python -m pip install --upgrade pip -r requirements.txt
echo    5) python -m streamlit run app.py
echo.
pause
endlocal