#!/bin/bash
set -e

if [ ! -f "venv/bin/activate" ]; then
  echo "Virtual environment not found. Please run ./install_mac.sh first."
  exit 1
fi

source venv/bin/activate
python3 run.py
