import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.routers import auth, device, admin
from app.tasks import run_aggregation, mark_stale_devices_offline

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        run_aggregation,
        IntervalTrigger(minutes=10),
        id="aggregate_stats",
        replace_existing=True,
    )
    scheduler.add_job(
        mark_stale_devices_offline,
        IntervalTrigger(minutes=1),
        id="mark_stale_devices_offline",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "APScheduler started — aggregation every 10 min, offline check every 1 min"
    )
    # Run once at startup to catch up
    run_aggregation()
    mark_stale_devices_offline()
    yield
    scheduler.shutdown()


app = FastAPI(title="Health Pose Assistant API", version="0.1.0", lifespan=lifespan)

settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(device.router)
app.include_router(admin.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
