.PHONY: run test compile up down logs restart backup health smoke check-apilogin issue-token

run:
	python3 -m src.main

test:
	pytest -q

compile:
	python3 -m compileall -q src tests scripts

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

restart: down up

backup:
	python3 scripts/backup_state.py

health:
	python3 scripts/healthcheck.py

smoke:
	PYTHONPATH=. python3 scripts/smoke_seller_api.py

check-apilogin:
	PYTHONPATH=. python3 scripts/check_apilogin.py

issue-token:
	PYTHONPATH=. python3 scripts/issue_access_token.py
