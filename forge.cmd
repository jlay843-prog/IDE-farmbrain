@echo off
setlocal
set ROOT=%~dp0
set PYTHONPATH=%ROOT%src;%PYTHONPATH%
py -3 -m forge %*
