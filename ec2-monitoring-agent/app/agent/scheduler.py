"""
Agent Scheduler — APScheduler pour le monitoring proactif.

Lance la boucle agent à intervalles réguliers.
Peut être contrôlé via l'API (start/stop/run-now).
"""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

# Module-level scheduler instance
_scheduler = None
_app = None

JOB_ID = "monitoring_cycle"


def init_scheduler(app):
    """Initialize the scheduler with the Flask app context."""
    global _scheduler, _app
    _app = app

    _scheduler = BackgroundScheduler(daemon=True)
    interval = app.config.get('MONITORING_INTERVAL_MINUTES', 5)

    _scheduler.add_job(
        func=_run_cycle,
        trigger=IntervalTrigger(minutes=interval),
        id=JOB_ID,
        name="AI Monitoring Cycle",
        replace_existing=True,
        max_instances=1  # Never run two cycles simultaneously
    )

    logger.info(f"Scheduler initialized — monitoring every {interval} minutes")


def start_scheduler():
    """Start the proactive monitoring scheduler."""
    if _scheduler and not _scheduler.running:
        _scheduler.start()
        logger.info("Scheduler STARTED — agent is now monitoring proactively")
        return True
    return False


def stop_scheduler():
    """Stop the proactive monitoring scheduler."""
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler STOPPED — agent is now idle")
        return True
    return False


def run_now():
    """Force an immediate monitoring cycle (does not affect the schedule)."""
    logger.info("Manual cycle triggered via API")
    return _run_cycle()


def get_scheduler_status() -> dict:
    """Get the current scheduler status."""
    if not _scheduler:
        return {"status": "not_initialized"}

    running = _scheduler.running
    job = _scheduler.get_job(JOB_ID)

    return {
        "status": "running" if running else "stopped",
        "interval_minutes": _app.config.get('MONITORING_INTERVAL_MINUTES', 5) if _app else None,
        "next_run": str(job.next_run_time) if job and job.next_run_time else None
    }


def _run_cycle():
    """Execute one agent monitoring cycle."""
    from app.agent.loop import run_agent_cycle

    if not _app:
        logger.error("Scheduler: Flask app not initialized")
        return None

    logger.info("Scheduler: starting monitoring cycle...")
    try:
        result = run_agent_cycle(_app)
        severity = result.get("severity", "unknown")
        logger.info(f"Scheduler: cycle complete — severity={severity}")
        return result
    except Exception as e:
        logger.error(f"Scheduler: cycle failed — {e}")
        return None
