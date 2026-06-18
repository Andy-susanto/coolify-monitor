'use strict';

/**
 * Util bersama untuk launcher Coolify Monitor.
 * Mereplikasi logika paths.py agar Node & Python berbagi lokasi config yang sama.
 */

const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const APP_NAME = 'CoolifyMonitor';
const PKG_ROOT = path.resolve(__dirname, '..');

function configDir() {
  let base;
  if (process.platform === 'darwin') {
    base = path.join(os.homedir(), 'Library', 'Application Support', APP_NAME);
  } else if (process.platform === 'win32') {
    base = path.join(process.env.APPDATA || os.homedir(), APP_NAME);
  } else {
    base = path.join(os.homedir(), '.config', 'coolify-monitor');
  }
  fs.mkdirSync(base, { recursive: true });
  return base;
}

function envFile() {
  return path.join(configDir(), '.env');
}

function venvDir() {
  return path.join(configDir(), 'venv');
}

function venvPython() {
  if (process.platform === 'win32') {
    return path.join(venvDir(), 'Scripts', 'python.exe');
  }
  return path.join(venvDir(), 'bin', 'python3');
}

/** Salin .env.example -> config/.env bila belum ada. */
function ensureEnv() {
  const target = envFile();
  if (!fs.existsSync(target)) {
    const example = path.join(PKG_ROOT, '.env.example');
    fs.writeFileSync(target, fs.existsSync(example) ? fs.readFileSync(example) : '');
  }
  return target;
}

/** Baca .env jadi objek key->value. */
function readEnv() {
  const f = envFile();
  const out = {};
  if (!fs.existsSync(f)) return out;
  for (const raw of fs.readFileSync(f, 'utf8').split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith('#') || !line.includes('=')) continue;
    const idx = line.indexOf('=');
    out[line.slice(0, idx).trim()] = line.slice(idx + 1).trim();
  }
  return out;
}

/** Tulis/ubah satu key di .env sambil mempertahankan komentar & urutan. */
function setEnv(key, value) {
  const f = ensureEnv();
  const lines = fs.readFileSync(f, 'utf8').split(/\r?\n/);
  let found = false;
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].trim().startsWith(`${key}=`)) {
      lines[i] = `${key}=${value}`;
      found = true;
      break;
    }
  }
  if (!found) lines.push(`${key}=${value}`);
  fs.writeFileSync(f, lines.join('\n').replace(/\n+$/, '') + '\n');
}

/** Cari interpreter python3 sistem (untuk membuat venv). */
function findSystemPython() {
  const candidates = process.platform === 'win32'
    ? ['python', 'python3', 'py']
    : ['python3', 'python'];
  for (const c of candidates) {
    const r = spawnSync(c, ['--version'], { encoding: 'utf8' });
    if (r.status === 0) return c;
  }
  return null;
}

/** Daftar dependency runtime per OS (tanpa tools build). */
function runtimeDeps() {
  const common = ['requests', 'python-dotenv', 'rich', 'Flask'];
  if (process.platform === 'darwin') return [...common, 'rumps'];
  return [...common, 'pystray', 'Pillow'];
}

module.exports = {
  APP_NAME,
  PKG_ROOT,
  configDir,
  envFile,
  venvDir,
  venvPython,
  ensureEnv,
  readEnv,
  setEnv,
  findSystemPython,
  runtimeDeps,
};
