.PHONY: run test up down logs
run:
	python3 -m app.server
test:
	python3 -m unittest discover -s tests -v
up:
	docker compose up --build -d
down:
	docker compose down
logs:
	docker compose logs -f app model-init
