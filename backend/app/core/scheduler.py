from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings
from app.services.retention import run_retention_job
from app.services.stagnant_detector import check_stagnant_hikers

scheduler = AsyncIOScheduler()


def start_scheduler() -> None:
    scheduler.add_job(
        check_stagnant_hikers,
        trigger="interval",
        minutes=settings.stagnant_check_interval_minutes,
        id="stagnant_check",
        replace_existing=True,
        # Default APScheduler cuma toleransi telat 1 detik sebelum job
        # di-skip ("missed"). Di Docker Desktop/WSL2 timer jitter beberapa
        # detik itu normal, jadi tanpa ini job-nya SELALU di-skip dan gak
        # pernah beneran jalan. 30 detik cukup longgar buat kasus ini.
        misfire_grace_time=30,
    )
    # Retensi data: harian pukul 03:30 waktu laptop. Tidak menghapus apa pun selama data_retention_days = 0 (bawaan).
    scheduler.add_job(run_retention_job, trigger="cron", hour=3, minute=30, id="retention", replace_existing=True,
                      misfire_grace_time=3600, coalesce=True)
    scheduler.start()


def reschedule_stagnant(minutes: int) -> None:
    """Terapkan interval pemeriksaan baru tanpa restart (dipanggil setelah pengaturan diubah)."""
    if not scheduler.running:
        return
    try:
        scheduler.reschedule_job("stagnant_check", trigger="interval", minutes=minutes)
    except JobLookupError:
        pass
