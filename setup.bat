@echo off
echo ===================================================
echo Setting up IAcine Virtual Avatar Services
echo ===================================================

echo.
echo [1/3] Setting up Backend Python Environment...
if not exist ".venv" (
    echo Creating virtual environment in .venv...
    python -m venv .venv
) else (
    echo Virtual environment .venv already exists.
)

echo Activating virtual environment and installing Python dependencies...
call .venv\Scripts\activate
cd back
pip install -r requirements.txt

echo Checking for .env file...
if not exist ".env" (
    if exist ".env.example" (
        echo Creating .env file from .env.example...
        copy .env.example .env
        echo IMPORTANT: Please edit back\.env and add your OPENAI_API_KEY.
    ) else (
        echo Warning: .env.example not found in back directory. Please create .env manually.
    )
) else (
    echo .env file already exists.
)
cd ..

echo.
echo [2/3] Setting up Frontend Node.js Environment...
cd front
echo Installing npm dependencies...
call npm install
cd ..

echo.
echo [3/3] Setting up SSL Certificates (mkcert required)
echo Make sure you have mkcert installed (https://github.com/FiloSottile/mkcert)
echo.
set /p IP_ADDR="Enter your local IPv4 address (e.g. 192.168.1.20) to generate certificates (or press Enter to skip): "

if not "%IP_ADDR%"=="" (
    echo Installing mkcert local CA...
    mkcert -install
    
    if not exist "front\certs" (
        mkdir front\certs
    )
    
    cd front\certs
    echo Generating certificates for localhost, 127.0.0.1, and %IP_ADDR%...
    mkcert localhost 127.0.0.1 %IP_ADDR%
    cd ..\..
    
    echo.
    echo =========================================================================
    echo IMPORTANT: Make sure the generated certificate names (e.g. %IP_ADDR%+2.pem) 
    echo match the ones hardcoded in front\vite.config.js and back\app\main.py
    echo =========================================================================
) else (
    echo Skipping certificate generation.
)

echo.
echo ===================================================
echo Setup complete! 
echo Please ensure you have set your OPENAI_API_KEY in back\.env
echo You can now run start.bat to launch the services.
echo ===================================================
pause
