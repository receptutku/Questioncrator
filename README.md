# Questioncrator

Havuz tabanlı otomatik soru üretim sistemi. Tasarım: `docs/tasarim-v0.5.md`.

## Kurulum

    python -m venv .venv
    source .venv/bin/activate
    pip install -e ".[dev]"

## Test

    pytest -q
    ruff check .

## Çalıştırma

    streamlit run questioncrator/app/main.py
