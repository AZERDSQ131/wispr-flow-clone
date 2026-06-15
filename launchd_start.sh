#!/bin/bash
# Attendre que la session GUI soit prête
sleep 8

SPILL_DIR="/Users/julesyzerd/Applications/Spill"
cd "$SPILL_DIR"

exec "$SPILL_DIR/.venv/bin/python3" -u "$SPILL_DIR/main.py"
