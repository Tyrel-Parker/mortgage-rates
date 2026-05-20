SHELL  := /bin/bash
DIR    := $(shell pwd)
VENV   := $(DIR)/.venv
PYTHON := $(VENV)/bin/python3
SCRIPT := $(DIR)/navyfed_irrrl_watch.py
LOG    := $(DIR)/irrrl_watch.log
STATE  := $(DIR)/irrrl_last_rate.json
MARKER := navyfed_irrrl_watch  # used to find/remove the cron entry
SCHED  := 0 9 * * 1-5          # weekdays at 9am — adjust as needed

.PHONY: install uninstall

install:
	@# --- .env ---
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		$(PYTHON) -c "\
data = open('.env').read(); \
data = __import__('re').sub(r'STATE_FILE=.*', 'STATE_FILE=$(STATE)', data); \
open('.env', 'w').write(data)"; \
		echo "  [ok] .env created — fill in NTFY_TOPIC, NTFY_SERVER, and TARGET_RATE before the cron runs"; \
	else \
		echo "  [skip] .env already exists"; \
	fi

	@# --- .gitignore ---
	@touch .gitignore
	@for entry in ".env" "irrrl_last_rate.json" "irrrl_watch.log" ".venv/"; do \
		if ! grep -qxF "$$entry" .gitignore; then \
			echo "$$entry" >> .gitignore; \
			echo "  [ok] added $$entry to .gitignore"; \
		else \
			echo "  [skip] $$entry already in .gitignore"; \
		fi; \
	done

	@# --- venv + pip deps ---
	@if [ ! -f "$(VENV)/bin/activate" ]; then \
		python3 -m venv $(VENV); \
		echo "  [ok] virtualenv created at .venv"; \
	else \
		echo "  [skip] virtualenv already exists"; \
	fi
	@$(PYTHON) -m pip install -q requests beautifulsoup4 python-dotenv
	@echo "  [ok] dependencies installed"

	@# --- cron ---
	@if crontab -l 2>/dev/null | grep -q "$(MARKER)"; then \
		echo "  [skip] cron job already exists"; \
	else \
		(crontab -l 2>/dev/null; echo "$(SCHED) $(PYTHON) $(SCRIPT) >> $(LOG) 2>&1  # $(MARKER)") | crontab -; \
		echo "  [ok] cron job added ($(SCHED))"; \
	fi

	@echo ""
	@echo "Done. Edit .env then run: $(PYTHON) $(SCRIPT)"

uninstall:
	@# --- cron ---
	@if crontab -l 2>/dev/null | grep -q "$(MARKER)"; then \
		crontab -l 2>/dev/null | grep -v "$(MARKER)" | crontab -; \
		echo "  [ok] cron job removed"; \
	else \
		echo "  [skip] no cron job found"; \
	fi

	@# --- state file ---
	@if [ -f "$(STATE)" ]; then \
		rm "$(STATE)"; \
		echo "  [ok] state file removed"; \
	else \
		echo "  [skip] no state file found"; \
	fi

	@echo ""
	@echo "Done. .env and the script are untouched — delete those manually if needed."