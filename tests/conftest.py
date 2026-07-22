import os

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://observability:observability@localhost:5436/observability",
)
