'use strict';

/**
 * Auto-start saat login, lintas OS:
 * - macOS  : LaunchAgent (~/Library/LaunchAgents)
 * - Windows: registry HKCU\...\Run (via reg.exe)
 * - Linux  : ~/.config/autostart/*.desktop
 *
 * Perintah yang didaftarkan: meluncurkan launcher ini dengan argumen `tray`.
 */

const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const LABEL = 'com.coolify.tray';
const RUN_NAME = 'CoolifyMonitor';

function launchArgv() {
  // node <cli.js> tray
  const cli = path.resolve(__dirname, 'cli.js');
  return [process.execPath, cli, 'tray'];
}

// ─── macOS ────────────────────────────────────────────────────────

function macPlistPath() {
  return path.join(os.homedir(), 'Library', 'LaunchAgents', `${LABEL}.plist`);
}

function macInstalled() {
  return fs.existsSync(macPlistPath());
}

function macInstall() {
  const [node, cli, arg] = launchArgv();
  const args = [node, cli, arg]
    .map((a) => `        <string>${a}</string>`)
    .join('\n');
  const plist = `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL}</string>
    <key>ProgramArguments</key>
    <array>
${args}
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>ProcessType</key>
    <string>Interactive</string>
</dict>
</plist>
`;
  fs.mkdirSync(path.dirname(macPlistPath()), { recursive: true });
  fs.writeFileSync(macPlistPath(), plist);
  spawnSync('launchctl', ['load', macPlistPath()]);
}

function macUninstall() {
  spawnSync('launchctl', ['unload', macPlistPath()]);
  try { fs.unlinkSync(macPlistPath()); } catch (_) {}
}

// ─── Windows ──────────────────────────────────────────────────────

function winCmd() {
  const [node, cli, arg] = launchArgv();
  return `"${node}" "${cli}" ${arg}`;
}

function winInstalled() {
  const r = spawnSync('reg', [
    'query', 'HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run',
    '/v', RUN_NAME,
  ], { encoding: 'utf8' });
  return r.status === 0;
}

function winInstall() {
  spawnSync('reg', [
    'add', 'HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run',
    '/v', RUN_NAME, '/t', 'REG_SZ', '/d', winCmd(), '/f',
  ]);
}

function winUninstall() {
  spawnSync('reg', [
    'delete', 'HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run',
    '/v', RUN_NAME, '/f',
  ]);
}

// ─── Linux ────────────────────────────────────────────────────────

function linuxDesktopPath() {
  return path.join(os.homedir(), '.config', 'autostart', 'coolify-monitor.desktop');
}

function linuxInstalled() {
  return fs.existsSync(linuxDesktopPath());
}

function linuxInstall() {
  const [node, cli, arg] = launchArgv();
  const content = `[Desktop Entry]
Type=Application
Name=Coolify Monitor
Exec=${node} ${cli} ${arg}
X-GNOME-Autostart-enabled=true
Terminal=false
`;
  fs.mkdirSync(path.dirname(linuxDesktopPath()), { recursive: true });
  fs.writeFileSync(linuxDesktopPath(), content);
}

function linuxUninstall() {
  try { fs.unlinkSync(linuxDesktopPath()); } catch (_) {}
}

// ─── API publik ───────────────────────────────────────────────────

function isInstalled() {
  if (process.platform === 'darwin') return macInstalled();
  if (process.platform === 'win32') return winInstalled();
  return linuxInstalled();
}

function enable() {
  if (process.platform === 'darwin') return macInstall();
  if (process.platform === 'win32') return winInstall();
  return linuxInstall();
}

function disable() {
  if (process.platform === 'darwin') return macUninstall();
  if (process.platform === 'win32') return winUninstall();
  return linuxUninstall();
}

module.exports = { isInstalled, enable, disable };
