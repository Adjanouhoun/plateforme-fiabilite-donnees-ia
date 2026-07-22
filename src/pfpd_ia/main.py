from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from pfpd_ia import __version__
from pfpd_ia.database import get_session

app = FastAPI(
    title="PFPD-IA",
    description="API du socle d'observabilite multi-pipelines",
    version=__version__,
)


@app.get("/health/live", tags=["health"])
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
def readiness(session: Annotated[Session, Depends(get_session)]) -> dict[str, str]:
    try:
        schema_ready = session.execute(
            text("SELECT to_regclass('observability.pipelines') IS NOT NULL")
        ).scalar_one()
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unavailable",
        ) from exc
    if not schema_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database schema unavailable",
        )
    return {"status": "ready", "database": "available"}
