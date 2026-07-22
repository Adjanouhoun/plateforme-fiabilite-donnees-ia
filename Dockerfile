FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --create-home app

COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --no-cache-dir . \
    && rm -rf build src/*.egg-info

COPY alembic.ini ./
COPY migrations ./migrations

USER app

EXPOSE 8000

CMD ["uvicorn", "pfpd_ia.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM runtime AS test

USER root
RUN python -m pip install --no-cache-dir ".[dev]"
COPY tests ./tests
USER app

CMD ["pytest", "-q"]
