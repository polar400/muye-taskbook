@echo off
cd /d "%~dp0.."
python -c "import sys,struct,tkinter; assert sys.version_info[:2] == (3,14) and struct.calcsize('P') == 8, 'Windows x64 Python 3.14 required'"
if errorlevel 1 goto failed
if exist vendor\maa\__init__.py if exist vendor\numpy\__init__.py goto pillow
python -m pip install --target vendor -r requirements.txt
if errorlevel 1 goto failed
:pillow
python -m pip install Pillow==12.2.0
if errorlevel 1 goto failed
python -c "import sys;sys.path.insert(0,'vendor');import tkinter,numpy,PIL;from maa.tasker import Tasker;print('Dependencies ready')"
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo Dependency installation failed. Check Python version and network.
pause
exit /b 1
