#!/bin/bash

# Check if virtual environment is active
if [[ -n "${VIRTUAL_ENV}" ]]; then
    deactivate
fi

if [ -d "venv" ]; then
    rm -rf venv
fi

python -m venv venv

source venv/bin/activate

pip install -r requirements.txt

python3 main.py