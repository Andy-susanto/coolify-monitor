'use strict';

/**
 * Smoke test lintas-OS untuk Coolify Monitor.
 *
 * Memverifikasi tanpa butuh koneksi Coolify nyata:
 *  - Deteksi platform & resolusi path config (Node)
 *  - Python interpreter & venv tersedia
 *  - Semua modul Python bisa diimpor
 *  - Modul tray yang benar untuk OS ini bisa diimpor (rumps / pystray)
 *  - Auto-start helper tidak error
 *
 * Jalankan:  node bin/smoke-test.js   atau   coolify-monitor smoke
 * Exit code 0 = semua lulus, 1 = ada yang gagal.
 */

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const lib = require('./lib');
const autostart = require('./autostart');

const c = {
  reset: '\x1b[0m', bold: '\x1b[1m', dim: '\x1b[2m',
  green: '\x1b[32m', red: '\x1b[31m', yellow: '\x1b[33m', cyan: '\x1b[36m',
};

let passed = 0;
let failed = 0;

function ok(name, detail = '') {
  passed++;
  console.log(`  ${c.green}✓${c.reset} ${name}${detail ? ` ${c.dim}${detail}${c.reset}` : ''}`);
}
function fail(name, detail = '') {
  failed++;
  console.log(`  ${c.red}✗${c.reset} ${name}${detail ? ` ${c.dim}${detail}${c.reset}` : ''}`);
}
function warn(name, detail = '') {
  console.log(`  ${c.yellow}!${c.reset} ${name}${detail ? ` ${c.dim}${detail}${c.reset}` : ''}`);
}

function section(title) {
  console.log(`\n${c.cyan}${c.bold}${title}${c.reset}`);
}

// Modul tray yang diharapkan per-OS (harus sinkron dengan cli.js#trayScript).
function expectedTray() {
  return process.platform === 'darwin'
    ? { script: 'tray_app.py', lib: 'rumps' }
    : { script: 'tray_app_win.py', lib: 'pystray' };
}

function run() {
  console.log(`${c.bold}Coolify Monitor — Smoke Test${c.reset}`);
  console.log(`${c.dim}OS: ${process.platform} (${process.arch}) | Node: ${process.version}${c.reset}`);

  // ─── 1. Node-side ──────────────────────────────
  section('1. Lingkungan Node & path');

  const cfg = lib.configDir();
  fs.existsSync(cfg) ? ok('Config dir dapat dibuat', cfg) : fail('Config dir gagal dibuat', cfg);

  const env = lib.ensureEnv();
  fs.existsSync(env) ? ok('.env siap', env) : fail('.env tidak terbuat', env);

  const tray = expectedTray();
  const trayPath = path.join(lib.PKG_ROOT, tray.script);
  fs.existsSync(trayPath)
    ? ok(`Tray script untuk ${process.platform}`, tray.script)
    : fail(`Tray script hilang`, tray.script);

  try {
    const status = autostart.isInstalled();
    ok('Auto-start helper berjalan', `status: ${status ? 'ON' : 'OFF'}`);
  } catch (e) {
    fail('Auto-start helper error', e.message);
  }

  // ─── 2. Python ─────────────────────────────────
  section('2. Python & venv');

  const sysPy = lib.findSystemPython();
  sysPy ? ok('Python sistem ditemukan', sysPy)
        : fail('Python sistem tidak ada', 'install Python 3.9+');

  const py = lib.venvPython();
  const hasVenv = fs.existsSync(py);
  hasVenv ? ok('venv ada', py)
          : warn('venv belum dibuat', 'jalankan: coolify-monitor doctor');

  // ─── 3. Import modul Python ────────────────────
  section('3. Import modul Python');

  const pyExe = hasVenv ? py : sysPy;
  if (!pyExe) {
    fail('Lewati import test', 'tidak ada interpreter Python');
    return summary();
  }

  // Modul inti lintas-OS (tanpa tray).
  const coreMods = ['paths', 'coolify_client', 'uptime_tracker', 'background_monitor', 'web.app'];
  const coreProbe = coreMods.map((m) => `import ${m}`).join('; ');
  const rCore = spawnSync(pyExe, ['-c', coreProbe], {
    cwd: lib.PKG_ROOT, encoding: 'utf8',
    env: { ...process.env, COOLIFY_ENV_FILE: env, PYTHONDONTWRITEBYTECODE: '1' },
  });
  rCore.status === 0
    ? ok('Modul inti dapat diimpor', coreMods.join(', '))
    : fail('Gagal impor modul inti', (rCore.stderr || '').trim().split('\n').pop());

  // Modul tray sesuai OS (butuh rumps/pystray; hanya jika venv ada).
  // Pakai find_spec agar tidak memicu backend GUI pystray di lingkungan headless.
  if (hasVenv) {
    const rTray = spawnSync(pyExe, ['-c',
      `import importlib.util, sys; sys.exit(0 if importlib.util.find_spec(${JSON.stringify(tray.lib)}) else 1)`,
    ], { cwd: lib.PKG_ROOT, encoding: 'utf8' });
    rTray.status === 0
      ? ok(`Library tray (${tray.lib}) terpasang`)
      : fail(`Library tray (${tray.lib}) tidak ada`, 'jalankan: coolify-monitor doctor');
  } else {
    warn(`Library tray (${tray.lib})`, 'lewati — venv belum ada');
  }

  return summary();
}

function summary() {
  console.log(`\n${c.bold}Hasil:${c.reset} ${c.green}${passed} lulus${c.reset}` +
    (failed ? `, ${c.red}${failed} gagal${c.reset}` : ''));
  if (failed === 0) {
    console.log(`${c.green}${c.bold}Semua cek dasar lulus untuk ${process.platform}.${c.reset}\n`);
  } else {
    console.log(`${c.red}Ada cek yang gagal — lihat detail di atas.${c.reset}\n`);
  }
  process.exitCode = failed === 0 ? 0 : 1;
}

module.exports = { run };

if (require.main === module) {
  run();
}
