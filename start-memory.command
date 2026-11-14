#!/bin/zsh
set -eu
cd "${0:A:h}"
# Verify Cloud before restarting the running Band worker; never start Docker.
.venv/bin/python memory_check.py
./service.sh restart
print 'Cognee Cloud access verified; bot restarted with the configured cloud dataset.'
