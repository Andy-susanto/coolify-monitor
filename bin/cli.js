#!/usr/bin/env node
'use strict';

/**
 * coolify-monitor — launcher npm lintas OS.
 *
 * Commands:
 *   coolify-monitor            menu interaktif (router)
 *   coolify-monitor setup      konfigurasi setting interaktif
 *   coolify-monitor start      jalankan tray app (default OS)
 *   coolify-monitor tray       alias start
 *   coolify-monitor monitor    jalankan monitor di foreground (tanpa tray)
 *   coolify-monitor dashboard  jalankan web dashboard saja
 *   coolify-monitor config     tampilkan konfigurasi saat ini
 *   coolify-monitor autostart [on|off]
 *   coolify-monitor doctor     cek environment Python & deps
 *   coolify-monitor help
 */

const path = require('path');
const fs = require('fs');
const http = require('http');
const readline = require('readline');
const { spawn } = require('child_process');

const lib = require('./lib');
const autostart = require('./autostart');
const { ensurePython } = require('./setup-python');

// ─── readline helpers ─────────────────────────────────────────────

function ask(question, { hidden = false } = {}) {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise((resolve) => {
    if (hidden) {
      const onData = (char) => {
        char = char.toString();
        if (['\n', '\r', '\u0004'].includes(char)) {
          process.stdout.write('\n');
          process.stdin.removeListener('data', onData);
        } else {
          process.stdout.clearLine(0);
          readline.cursorTo(process.stdout, 0);
          process.stdout.write(question + '*'.repeat(rl.line.length));
        }
      };
      process.stdin.on('data', onData);
    }
    rl.question(question, (answer) => {
      rl.close();
      resolve(answer.trim());
    });
  });
}

// ─── styling ──────────────────────────────────────────────────────

const c = {
  reset: '\x1b[0m', bold: '\x1b[1m', dim: '\x1b[2m',
  cyan: '\x1b[36m', green: '\x1b[32m', yellow: '\x1b[33m',
  red: '\x1b[31m', magenta: '\x1b[35m',
};
const banner = () => {
  console.log(`${c.magenta}${c.bold}
  ╔════════════════════════════════════╗
  ║        Coolify Monitor             ║
  ╚════════════════════════════════════╝${c.reset}`);
};

function maskSecret(v) {
  if (!v) return `${c.dim}(belum diisi)${c.reset}`;
  if (v.length <= 6) return '••••';
  return v.slice(0, 3) + '•'.repeat(Math.max(4, v.length - 6)) + v.slice(-3);
}

// ─── run python ───────────────────────────────────────────────────

function runPython(scriptRel, extraArgs = [], { detached = false, stdio = 'inherit' } = {}) {
  // First-run (venv belum ada): tampilkan progres setup agar tidak terkesan hang.
  const firstRun = !fs.existsSync(lib.venvPython());
  if (firstRun) {
    console.log(`${c.dim}Penyiapan awal: membuat Python environment & dependency (sekali saja)…${c.reset}`);
  }
  const py = ensurePython({ quiet: !firstRun });
  const script = path.join(lib.PKG_ROOT, scriptRel);
  const env = {
    ...process.env,
    COOLIFY_ENV_FILE: lib.envFile(),
    PYTHONDONTWRITEBYTECODE: '1',
  };
  if (detached) {
    const child = spawn(py, [script, ...extraArgs], {
      cwd: lib.PKG_ROOT, env, detached: true, stdio: 'ignore',
    });
    child.unref();
    return child;
  }
  const child = spawn(py, [script, ...extraArgs], {
    cwd: lib.PKG_ROOT, env, stdio,
  });
  return child;
}

function trayScript() {
  // macOS: rumps (tray_app.py). Windows & Linux: pystray (tray_app_win.py).
  return process.platform === 'darwin' ? 'tray_app.py' : 'tray_app_win.py';
}

/** Buka URL di browser default lintas-OS. */
function openBrowser(url) {
  const cmd = process.platform === 'darwin' ? 'open'
            : process.platform === 'win32' ? 'cmd' : 'xdg-open';
  const args = process.platform === 'win32' ? ['/c', 'start', '', url] : [url];
  try {
    const child = spawn(cmd, args, { detached: true, stdio: 'ignore' });
    child.unref();
  } catch (_) { /* abaikan; URL tetap ditampilkan di terminal */ }
}

/** Tunggu sampai web server merespon (HTTP), atau timeout. */
function waitForServer(url, timeoutMs = 30000) {
  const start = Date.now();
  return new Promise((resolve) => {
    const tryOnce = () => {
      const req = http.get(url, (res) => {
        res.resume();
        resolve(true);
      });
      req.on('error', () => {
        if (Date.now() - start > timeoutMs) return resolve(false);
        setTimeout(tryOnce, 400);
      });
      req.setTimeout(2000, () => req.destroy());
    };
    tryOnce();
  });
}

/** Mode dashboard (9router style): start web+monitor sebagai engine background,
 *  lalu tampilkan menu interaktif: Buka Dashboard / Hide to Tray / Exit. */
async function runDashboard() {
  const env = lib.readEnv();
  const port = env.WEB_PORT || '5555';
  const url = `http://localhost:${port}`;
  const configured = env.COOLIFY_URL && env.COOLIFY_API_KEY &&
    env.COOLIFY_API_KEY !== 'your-api-key-here';

  banner();
  console.log(`${c.dim}  Menjalankan Coolify Monitor…${c.reset}`);

  // Start engine (web server + monitor in-process) sebagai child, log disenyapkan.
  const engine = runPython('web/app.py', [], { stdio: 'ignore' });

  const up = await waitForServer(url);
  if (!up) {
    console.log(`${c.red}  Gagal menjalankan server di ${url}.${c.reset}`);
    console.log(`  ${c.dim}Cek apakah port ${port} sudah dipakai, atau jalankan: coolify-monitor doctor${c.reset}\n`);
    try { engine.kill(); } catch (_) {}
    return;
  }

  console.log(`${c.green}  ● Coolify Monitor aktif${c.reset}  ${c.dim}${url}${c.reset}`);
  if (!configured) {
    console.log(`${c.yellow}  Konfigurasi belum lengkap — buka Dashboard lalu isi halaman Settings.${c.reset}`);
  }
  // Auto-buka browser sekali di awal (mirip 9router).
  openBrowser(configured ? url : `${url}/settings`);

  let action = 'quit';

  // Menu interaktif loop.
  // eslint-disable-next-line no-constant-condition
  while (true) {
    console.log(`
  ${c.bold}1${c.reset}) Buka Dashboard       ${c.dim}(${url})${c.reset}
  ${c.bold}2${c.reset}) Hide to Tray         ${c.dim}(jalan di background)${c.reset}
  ${c.bold}3${c.reset}) Exit                 ${c.dim}(hentikan monitor)${c.reset}`);
    const choice = await ask('\n  Pilih > ');
    if (choice === '1') {
      openBrowser(url);
      console.log(`${c.dim}  Membuka ${url} di browser…${c.reset}`);
    } else if (choice === '2') {
      action = 'tray';
      break;
    } else if (choice === '3' || choice === '0' || choice === 'q') {
      action = 'quit';
      break;
    } else {
      console.log(`${c.red}  Pilihan tidak dikenal.${c.reset}`);
    }
  }

  // Hentikan engine CLI.
  try { engine.kill('SIGTERM'); } catch (_) {}

  if (action === 'tray') {
    // Luncurkan tray sebagai proses detached (tray auto-start monitor+web sendiri).
    console.log(`${c.green}  Berpindah ke tray. Coolify Monitor tetap jalan di background.${c.reset}`);
    console.log(`  ${c.dim}Klik ikon di menu bar / system tray untuk kontrol. Quit dari sana untuk berhenti.${c.reset}\n`);
    runPython(trayScript(), [], { detached: true });
  } else {
    console.log(`${c.dim}  Coolify Monitor dihentikan. Sampai jumpa.${c.reset}\n`);
  }
}

// ─── settings definisi ────────────────────────────────────────────

const SETTINGS_GROUPS = [
  {
    title: 'Koneksi Coolify',
    items: [
      { key: 'COOLIFY_URL', label: 'Coolify URL', placeholder: 'https://coolify.example.com' },
      { key: 'COOLIFY_API_KEY', label: 'API Key', secret: true, placeholder: 'token dari Settings → API' },
    ],
  },
  {
    title: 'Monitor & Alert',
    items: [
      { key: 'POLL_INTERVAL', label: 'Poll interval (detik)', default: '30', number: true },
      { key: 'ALERT_ON_RECOVERY', label: 'Alert saat pulih (true/false)', default: 'true', bool: true },
    ],
  },
  {
    title: 'Web Dashboard',
    items: [
      { key: 'WEB_PORT', label: 'Port dashboard', default: '5555', number: true },
      { key: 'MONITOR_PASSWORD', label: 'Password dashboard (kosong = tanpa auth)', secret: true },
    ],
  },
];

async function editGroup(group) {
  const env = lib.readEnv();
  console.log(`\n${c.cyan}${c.bold}${group.title}${c.reset}`);
  for (const item of group.items) {
    const current = env[item.key] || '';
    const shown = item.secret ? maskSecret(current) : (current || `${c.dim}(${item.default || 'kosong'})${c.reset}`);
    const ph = item.placeholder ? ` ${c.dim}[${item.placeholder}]${c.reset}` : '';
    const ans = await ask(`  ${item.label}${ph}\n  ${c.dim}sekarang:${c.reset} ${shown}\n  > `, { hidden: item.secret });
    if (ans === '') continue; // skip, biarkan nilai lama
    let val = ans;
    if (item.bool) val = /^(y|yes|true|1|on)$/i.test(ans) ? 'true' : 'false';
    if (item.number && !/^\d+$/.test(ans)) {
      console.log(`  ${c.red}Diabaikan: harus angka.${c.reset}`);
      continue;
    }
    lib.setEnv(item.key, val);
    console.log(`  ${c.green}✓ tersimpan${c.reset}`);
  }
}

async function setupWizard() {
  banner();
  lib.ensureEnv();
  console.log(`${c.dim}Config disimpan di: ${lib.envFile()}${c.reset}`);
  for (const group of SETTINGS_GROUPS) {
    await editGroup(group);
  }
  // Auto-start
  const installed = autostart.isInstalled();
  const ans = await ask(`\n${c.cyan}Auto-start saat login?${c.reset} (${installed ? 'sekarang AKTIF' : 'sekarang NONAKTIF'}) [y/n, kosong=skip] > `);
  if (/^y/i.test(ans)) { autostart.enable(); console.log(`  ${c.green}✓ auto-start diaktifkan${c.reset}`); }
  else if (/^n/i.test(ans)) { autostart.disable(); console.log(`  ${c.green}✓ auto-start dimatikan${c.reset}`); }
  console.log(`\n${c.green}${c.bold}Setup selesai.${c.reset} Jalankan: ${c.bold}coolify-monitor start${c.reset}\n`);
}

// ─── config view ──────────────────────────────────────────────────

function showConfig() {
  const env = lib.readEnv();
  banner();
  console.log(`${c.dim}File: ${lib.envFile()}${c.reset}\n`);
  const rows = [
    ['Coolify URL', env.COOLIFY_URL || '-'],
    ['API Key', env.COOLIFY_API_KEY ? maskSecret(env.COOLIFY_API_KEY) : '-'],
    ['Poll interval', (env.POLL_INTERVAL || '30') + 's'],
    ['Alert on recovery', env.ALERT_ON_RECOVERY || 'true'],
    ['Web port', env.WEB_PORT || '5555'],
    ['Dashboard auth', env.MONITOR_PASSWORD ? 'aktif (password set)' : 'nonaktif'],
    ['Auto-start', autostart.isInstalled() ? 'aktif' : 'nonaktif'],
  ];
  for (const [k, v] of rows) console.log(`  ${c.bold}${k.padEnd(20)}${c.reset} ${v}`);
  console.log();
}

// ─── interactive router (menu) ────────────────────────────────────

async function mainMenu() {
  // loop sampai user keluar
  // eslint-disable-next-line no-constant-condition
  while (true) {
    banner();
    const on = autostart.isInstalled();
    console.log(`
  ${c.bold}1${c.reset}) Jalankan Tray App
  ${c.bold}2${c.reset}) Jalankan Monitor (foreground)
  ${c.bold}3${c.reset}) Buka Web Dashboard
  ${c.bold}4${c.reset}) Setting / Konfigurasi
  ${c.bold}5${c.reset}) Lihat Konfigurasi
  ${c.bold}6${c.reset}) Auto-start saat login [${on ? c.green + 'ON' : c.dim + 'OFF'}${c.reset}]
  ${c.bold}7${c.reset}) Doctor (cek environment)
  ${c.bold}0${c.reset}) Keluar
`);
    const choice = await ask('  Pilih > ');
    switch (choice) {
      case '1':
        console.log(`${c.dim}Meluncurkan tray... (Ctrl+C untuk berhenti)${c.reset}`);
        await waitChild(runPython(trayScript()));
        break;
      case '2':
        console.log(`${c.dim}Monitor berjalan... (Ctrl+C untuk berhenti)${c.reset}`);
        await waitChild(runPython('background_monitor.py'));
        break;
      case '3':
        console.log(`${c.dim}Dashboard berjalan... (Ctrl+C untuk berhenti)${c.reset}`);
        await waitChild(runPython('web/app.py'));
        break;
      case '4': await setupWizard(); break;
      case '5': showConfig(); await ask(`${c.dim}Enter untuk lanjut...${c.reset}`); break;
      case '6':
        if (autostart.isInstalled()) { autostart.disable(); console.log(`${c.green}Auto-start dimatikan.${c.reset}`); }
        else { autostart.enable(); console.log(`${c.green}Auto-start diaktifkan.${c.reset}`); }
        await ask(`${c.dim}Enter untuk lanjut...${c.reset}`);
        break;
      case '7': doctor(); await ask(`${c.dim}Enter untuk lanjut...${c.reset}`); break;
      case '0': case 'q': case '':
        console.log('Sampai jumpa.');
        return;
      default:
        console.log(`${c.red}Pilihan tidak dikenal.${c.reset}`);
    }
  }
}

function waitChild(child) {
  return new Promise((resolve) => {
    child.on('exit', () => resolve());
    child.on('error', () => resolve());
  });
}

// ─── doctor ───────────────────────────────────────────────────────

function doctor() {
  banner();
  const sysPy = lib.findSystemPython();
  console.log(`  Node            ${process.version}`);
  console.log(`  Platform        ${process.platform}`);
  console.log(`  System Python   ${sysPy || c.red + 'tidak ditemukan' + c.reset}`);
  console.log(`  venv            ${lib.venvDir()}`);
  console.log(`  Config          ${lib.envFile()}`);
  console.log(`\n  Menyiapkan / memverifikasi Python env...`);
  ensurePython({ quiet: false });
}

// ─── help ─────────────────────────────────────────────────────────

function help() {
  banner();
  console.log(`
  ${c.bold}Penggunaan:${c.reset} coolify-monitor [command]

  ${c.cyan}(tanpa arg)${c.reset}   start dashboard + monitor, auto-buka browser
  ${c.cyan}start${c.reset}        sama dengan (tanpa arg) — mode dashboard
  ${c.cyan}dashboard${c.reset}    sama dengan start
  ${c.cyan}menu${c.reset}         menu interaktif di terminal
  ${c.cyan}setup${c.reset}        konfigurasi setting via terminal
  ${c.cyan}tray${c.reset}         jalankan tray icon (opsional)
  ${c.cyan}monitor${c.reset}      jalankan monitor di foreground (tanpa web)
  ${c.cyan}config${c.reset}       tampilkan konfigurasi
  ${c.cyan}autostart${c.reset}    on | off
  ${c.cyan}doctor${c.reset}       cek environment Python & deps
  ${c.cyan}smoke${c.reset}        smoke test lintas-OS (verifikasi cepat)
  ${c.cyan}help${c.reset}         tampilkan bantuan ini
`);
}

// ─── entry ────────────────────────────────────────────────────────

async function main() {
  const [cmd, sub] = process.argv.slice(2);
  switch (cmd) {
    case undefined: case 'start': case 'dashboard': await runDashboard(); break;
    case 'menu': await mainMenu(); break;
    case 'setup': await setupWizard(); break;
    case 'tray': await waitChild(runPython(trayScript())); break;
    case 'monitor': await waitChild(runPython('background_monitor.py')); break;
    case 'config': showConfig(); break;
    case 'autostart':
      if (sub === 'on') { autostart.enable(); console.log('Auto-start diaktifkan.'); }
      else if (sub === 'off') { autostart.disable(); console.log('Auto-start dimatikan.'); }
      else console.log('Pakai: coolify-monitor autostart on|off  (status: ' + (autostart.isInstalled() ? 'ON' : 'OFF') + ')');
      break;
    case 'doctor': doctor(); break;
    case 'smoke': require('./smoke-test').run(); break;
    case 'help': case '--help': case '-h': help(); break;
    default:
      console.log(`Command tidak dikenal: ${cmd}`);
      help();
      process.exit(1);
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
