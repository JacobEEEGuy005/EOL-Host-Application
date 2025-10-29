from fastapi import APIRouter
from backend import metrics

router = APIRouter()


@router.get("/api/metrics")
def get_metrics():
    """Return current in-memory metrics counters."""
    try:
        return metrics.get_all()
    except Exception:
        return {}
