@echo off
python -m earhart run convoy-lands.kinner.json --lib lib
python -m earhart compile convoy-lands.kinner.json --target python --lib lib
