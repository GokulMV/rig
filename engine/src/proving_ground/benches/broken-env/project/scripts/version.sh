#!/bin/bash
set -e
cd "$(dirname "$0")/.."
PYTHONPATH=src python3 -c "from inventory._build import VERSION; print(VERSION)"
