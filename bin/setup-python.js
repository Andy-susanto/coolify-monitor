'use strict';

/**
 * Membuat Python venv di config dir & menginstal dependency runtime.
 * Idempotent: kalau venv & deps sudah ada, langsung lewati.
 */

const fs = require('fs');
const { spawnSync } = require('child_process');
const lib = require('./lib');

function run(cmd, args, opts = {}) {
  return spawnSync(cmd, args, { stdio: 'inherit', ...opts });
}

/** Cek apakah dependency inti sudah terpasang di venv. */
function depsInstalled(py) {
  const probe = process.platform === 'darwin'
    ? 'import flask, requests, dotenv, rumps'
    : 'import flask, requests, dotenv, pystray, PIL';
  const r = spawnSync(py, ['-c', probe], { encoding: 'utf8' });
  return r.status === 0;
}

function ensurePython({ quiet = false } = {}) {
  const py = lib.venvPython();
  const log = (m) => { if (!quiet) console.log(m); };

  if (fs.existsSync(py) && depsInstalled(py)) {
    log('Python environment siap.');
    return py;
  }

  const sysPy = lib.findSystemPython();
  if (!sysPy) {
    console.error(
      '\nPython 3 tidak ditemukan. Install Python 3.9+ dulu:\n' +
      '  macOS : brew install python3\n' +
      '  Windows: https://www.python.org/downloads/\n' +
      '  Linux : sudo apt install python3 python3-venv\n'
    );
    process.exit(1);
  }

  if (!fs.existsSync(py)) {
    log(`Membuat virtual environment di ${lib.venvDir()} ...`);
    const v = run(sysPy, ['-m', 'venv', lib.venvDir()]);
    if (v.status !== 0) {
      console.error('Gagal membuat venv.');
      process.exit(1);
    }
  }

  log('Menginstal dependency (pip) ...');
  run(py, ['-m', 'pip', 'install', '--upgrade', 'pip', '--quiet']);
  const deps = lib.runtimeDeps();
  const inst = run(py, ['-m', 'pip', 'install', '--quiet', ...deps]);
  if (inst.status !== 0) {
    console.error('Gagal menginstal dependency Python.');
    process.exit(1);
  }

  lib.ensureEnv();
  log('Setup selesai.');
  return py;
}

module.exports = { ensurePython };

if (require.main === module) {
  ensurePython();
}
