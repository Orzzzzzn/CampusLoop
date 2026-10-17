FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOST=0.0.0.0 PORT=8000 DATABASE_PATH=/app/data/heky.sqlite3
WORKDIR /app
RUN groupadd --gid 10001 campusloop && useradd --uid 10001 --gid campusloop --no-create-home campusloop && mkdir /app/data && chown campusloop:campusloop /app/data
COPY --chown=campusloop:campusloop app /app/app
COPY --chown=campusloop:campusloop static /app/static
COPY --chown=campusloop:campusloop knowledge /app/knowledge
USER campusloop
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"
CMD ["python", "-m", "app.server"]
