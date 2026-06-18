'use strict';

/**
 * postinstall — dijalankan otomatis setelah `npm install`.
 * Menyiapkan Python venv + dependency. Tidak menggagalkan install bila Python
 * belum ada; cukup beri pesan agar user menjalankan `coolify-monitor setup`.
 */

try {
  if (process.env.COOLIFY_SKIP_POSTINSTALL === '1') {
    process.exit(0);
  }
  const { ensurePython } = require('./setup-python');
  ensurePython({ quiet: false });
  console.log('\nSiap! Jalankan:  coolify-monitor setup   (konfigurasi)\n            atau:  coolify-monitor start   (jalankan)\n');
} catch (e) {
  console.warn(
    '\n[coolify-monitor] Setup Python belum tuntas: ' + e.message +
    '\nJalankan manual nanti: coolify-monitor setup\n'
  );
  // Jangan gagalkan npm install.
  process.exit(0);
}
