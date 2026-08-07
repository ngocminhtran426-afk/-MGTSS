@echo off
echo Starting application...

:: You can modify this to call a specific conda env if needed
:: call "C:\Users\hauho\anaconda3\condabin\conda.bat" activate myenv

python -m streamlit run st.py

pause
