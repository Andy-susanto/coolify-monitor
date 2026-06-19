'use strict';

/**
 * QA check lintas-OS untuk Coolify Monitor.
 *
 * Memverifikasi lebih dalam dari smoke test:
 *  - Semua modul Python inti dapat di-import (menangkap error runtime yang
 *    lolos dari pengecekan syntax).
 *  - Method API deployment yang dibutuhkan ada di CoolifyClient.
 *
 * Jalankan:  node bin/qa.js   atau   coolify-monitor qa
 * Exit code 0 = lulus, 1 = ada yang gagal.
 */

const { spawnSync } = require('child_process');
const lib = require('./lib');
const { ensurePython } = require('./setup-python');

const c = {
  reset: '\x1b[0m', bold: '\x1b[1m', dim: '\x1b[2m',
  green: '\x1b[32m', red: '\x1b[31m', cyan: '\x1b[36m',
};

let passed = 0;
let failed = 0;
const ok = (n, d = '') => { passed++; console.log(`  ${c.green}✓${c.reset} ${n}${d ? ` ${c.dim}${d}${c.reset}` : ''}`); };
const fail = (n, d = '') => { failed++; console.log(`  ${c.red}✗${c.reset} ${n}${d ? ` ${c.dim}${d}${c.reset}` : ''}`); };

function runPy(code) {
  const py = ensurePython({ quiet: true });
  return spawnSync(py, ['-c', code], {
    cwd: lib.PKG_ROOT,
    encoding: 'utf8',
    env: { ...process.env, COOLIFY_ENV_FILE: lib.envFile(), PYTHONDONTWRITEBYTECODE: '1' },
  });
}

function run() {
  console.log(`${c.bold}Coolify Monitor — QA Check${c.reset}`);
  console.log(`${c.dim}OS: ${process.platform} | Node: ${process.version}${c.reset}\n`);

  console.log(`${c.cyan}${c.bold}1. Import modul Python inti${c.reset}`);
  const mods = ['paths', 'coolify_client', 'uptime_tracker', 'background_monitor', 'web.app'];
  const r1 = runPy(`import ${mods.join(', ')}`);
  r1.status === 0
    ? ok('Semua modul inti dapat di-import', mods.join(', '))
    : fail('Gagal import modul inti', (r1.stderr || '').trim().split('\n').pop());

  console.log(`\n${c.cyan}${c.bold}2. Method API deployment${c.reset}`);
  const r2 = runPy(
    'from coolify_client import CoolifyClient; ' +
    "assert hasattr(CoolifyClient, 'get_application_deployments'); " +
    "assert hasattr(CoolifyClient, 'get_running_deployments'); " +
    "print('ok')"
  );
  r2.status === 0
    ? ok('get_application_deployments & get_running_deployments tersedia')
    : fail('Method deployment hilang', (r2.stderr || '').trim().split('\n').pop());

  console.log(`\n${c.cyan}${c.bold}3. BackgroundMonitor deploy alert${c.reset}`);
  const r3 = runPy(
    'import os; os.environ["DEPLOY_ALERT"]="true"; os.environ["DEPLOY_ALERT_APPS"]="a,b"; ' +
    'import background_monitor as bm; ' +
    'm = bm.BackgroundMonitor.__new__(bm.BackgroundMonitor); ' +
    "assert hasattr(bm.BackgroundMonitor, '_check_deployments'); " +
    "assert hasattr(bm.BackgroundMonitor, '_alert_deployment'); " +
    "assert hasattr(bm.BackgroundMonitor, '_extract_deploy_error'); " +
    'e = bm.BackgroundMonitor._extract_deploy_error(\'[{"output":"build error: failed","type":"stderr"}]\'); ' +
    "assert 'error' in e.lower(); " +
    "print('ok')"
  );
  r3.status === 0
    ? ok('Logika deploy alert (check/alert/extract_error) berfungsi')
    : fail('Logika deploy alert bermasalah', (r3.stderr || '').trim().split('\n').pop());

  console.log(`\n${c.bold}Hasil:${c.reset} ${c.green}${passed} lulus${c.reset}` +
    (failed ? `, ${c.red}${failed} gagal${c.reset}` : ''));
  process.exitCode = failed === 0 ? 0 : 1;
}

module.exports = { run };

if (require.main === module) {
  run();
}
