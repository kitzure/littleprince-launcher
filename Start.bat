@echo off
:: ===========================================================================
::  Little Prince Launcher
::
::  Double-click this file.  It opens the window that runs everything: the CD
::  games' server, Little Prince Online, the accounts website and the profile
::  editor.  The window asks Windows for administrator rights by itself (the
::  hosts redirect and port 80 need them) - answer Yes at the prompt.
::
::  Nothing else in this folder needs to be started by hand.
:: ===========================================================================
setlocal
cd /d "%~dp0"
title Little Prince Launcher

:: -- find a windowless Python ----------------------------------------------
set "PY="
for /f "delims=" %%p in ('where pythonw.exe 2^>nul') do if not defined PY set "PY=%%p"
if not defined PY for /f "delims=" %%p in ('where pyw.exe 2^>nul') do if not defined PY set "PY=%%p"
if not defined PY for /f "delims=" %%p in ('where python.exe 2^>nul') do if not defined PY set "PY=%%p"
if not defined PY goto :no_python

:: -- open the window --------------------------------------------------------
:: The launcher raises the administrator prompt itself.  Doing it here relaunched
:: this file by its path, and from a subst or mapped network drive the elevated
:: copy cannot see that drive - so it closed at once and nothing opened.
start "" "%PY%" "%~dp0Start_Server_GUI.pyw"
exit /b 0

:no_python
powershell -NoProfile -Command "Add-Type -AssemblyName PresentationFramework; $m='Python is not installed, or not on PATH.'+[char]10+[char]10+'The patcher needs Python 3 - the free build from python.org.'+[char]10+[char]10+'Tick \"Add python.exe to PATH\" while installing.'+[char]10+[char]10+'Open the download page now?'; $r=[System.Windows.MessageBox]::Show($m,'Python not found','YesNo','Warning'); if($r -eq 'Yes'){Start-Process 'https://www.python.org/downloads/windows/'}"
exit /b 1
