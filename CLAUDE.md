# Questioncrator — ajan talimatları

- **Commit ve push:** Commit mesajlarına `Co-Authored-By: Claude ...` ya da benzeri hiçbir iz/imza satırı ekleme. PR açıklamalarına da "Generated with Claude Code" gibi satır ekleme.
- Commit mesajları Türkçe, conventional biçim (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`).
- Testler: `.venv/bin/pytest -q`, lint: `.venv/bin/ruff check .`.
- `questioncrator/**/*.py` içinde konuya özel kelime geçmez (bkz. `tests/test_topic_agnostic.py`).
- Spec: `docs/superpowers/specs/2026-09-15-urun-v1-design.md`.
