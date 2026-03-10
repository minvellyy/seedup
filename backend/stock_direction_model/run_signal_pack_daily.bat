@echo off
setlocal

REM ====== (A) 프로젝트 루트로 이동 ======
cd /d "C:\Users\Admin\gg_drive\kpmg_7th_lab\stock_direction_model"

REM ====== (B) 로그 폴더 보장 ======
if not exist "logs" mkdir "logs"

REM ====== (C) conda env 활성화 ======
call "C:\Users\Admin\miniconda3\Scripts\activate.bat" pp_env

REM ====== (D) 실행 + 로그 저장 ======
python -m agents.signal_pack_agent >> "logs\signal_pack_daily.log" 2>&1

REM ====== (E) 종료 ======
endlocal