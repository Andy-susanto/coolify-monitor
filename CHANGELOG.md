# Changelog

## Cleanup & Refactor

### Dihapus (file tidak terpakai — nol referensi)
- `assets/coolify-logo.svg` — tidak direferensikan di mana pun (build hanya pakai `coolify.png`/`.ico`/`.icns`).
- `scripts/agent_compose_final.yaml` — file compose yatim, tidak dibaca skrip mana pun.
- `monitor-agent/Dockerfile.v2` + `monitor-agent/agent_v2.py` — varian agent tidak dipakai compose/CI; canonical adalah `agent.py`.
- `monitor-agent/Dockerfile.mini` + `monitor-agent/agent_mini.py` — varian agent tidak dipakai compose/CI.

### Refaktor (konservatif, perilaku tetap)
- Helper baca/tulis `.env` yang terduplikasi di `tray_app.py` & `tray_app_win.py` diekstrak ke `paths.py`
  (`read_env_value` / `set_env_value`) lalu dipakai bersama.
