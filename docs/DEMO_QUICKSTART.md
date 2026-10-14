# Contributor demo quickstart

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
pytest -q
python scripts/demo_runtime.py
```

No `.env`, Telegram bot, GGSEL account or DigiSeller account is required for the fake runtime.

Use `scripts/demo_pricing.py` for a single decision and `scripts/demo_runtime.py` for several in-memory pricing cycles.
