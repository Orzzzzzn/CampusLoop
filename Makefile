.PHONY: run test up down logs reset-demo
run:
	python3 -m app.server
test:
	PYTHONPATH=tests:. python3 -m unittest discover -s tests -v
up:
	docker compose up --build -d
down:
	docker compose down
logs:
	docker compose logs -f app model-init
# Wipe only the ride/account SQLite volume, keep Ollama models, then rebuild.
# Use this before a clean Kate → Yelyn → Hannah → Emily demo.
reset-demo:
	@echo "Stopping app and deleting the CampusLoop database volume (Ollama models are kept)…"
	docker compose stop app
	docker compose rm -f app
	@project=$${COMPOSE_PROJECT_NAME:-$$(basename "$$(pwd)" | tr '[:upper:]' '[:lower:]')}; \
	vol="$${project}_heky_data"; \
	if docker volume inspect "$$vol" >/dev/null 2>&1; then echo "Removing $$vol"; docker volume rm "$$vol"; \
	else echo "No $$vol volume found (already clean)."; fi
	docker compose up --build -d
	@echo "Fresh demo DB will seed Kate/Yelyn/Hannah/Emily/Noah with zero applications."
	@echo "Open http://127.0.0.1:$${HEKY_PORT:-8010} and hard-refresh (Cmd+Shift+R)."
