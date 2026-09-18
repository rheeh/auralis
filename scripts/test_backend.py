#!/usr/bin/env python3
"""Run unittest with disposable config/database and no external network."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='auralis-tests-') as config:
    env = dict(os.environ, AURALIS_CONFIG_DIR=config, AURALIS_TEST_OFFLINE='1',
               PYTHONDONTWRITEBYTECODE='1',
               PYTHONPATH=os.pathsep.join([str(root / 'scripts/offline'), str(root / 'SonicVale'), str(root / 'SonicVale/tests')]))
    args = sys.argv[1:] or ['discover', '-s', 'tests', '-p', 'test_*.py']
    result = subprocess.run([sys.executable, '-m', 'unittest', *args], cwd=root / 'SonicVale', env=env)
    sys.exit(result.returncode)
