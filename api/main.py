"""FastAPI entrypoint for the Portfolio Tracker API."""

from contextlib import asynccontextmanager
from threading import Thread

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import portfolio


def _background_price_fetch():
    """Fetch missing/stale price history in background. Keeps retrying."""
    import time
    from config import DB_PATH
    from database import get_connection
    from api.services.price_gaps import detect_price_gaps, has_gaps
    from api.cache import cache

    while True:
        try:
            conn = get_connection()
            try:
                gaps = detect_price_gaps(conn)
            finally:
                conn.close()
            if not has_gaps(gaps):
                print("Price data is current. Background fetch complete.")
                return
            print(
                f"Fetching price gaps: {len(gaps['missing'])} new, "
                f"{len(gaps['stale'])} stale securities..."
            )
            from fetch_price_history import update_price_history
            update_price_history(db_path=DB_PATH, delay=0.25)
            cache.invalidate_on_price_update()
            # Re-check after fetch
            conn = get_connection()
            try:
                gaps = detect_price_gaps(conn)
            finally:
                conn.close()
            if not has_gaps(gaps):
                print("Background price fetch complete.")
                return
        except Exception as e:
            print(f"Background price fetch failed (will retry): {e}")
        time.sleep(60)


def _live_price_loop():
    """Refresh live prices every 15 minutes while the app is active."""
    from api.services.live_prices import live_price_loop
    live_price_loop(interval_seconds=900.0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: consolidate new files, fetch price gaps in background."""
    from config import DB_PATH, DOCUMENTS_DIR
    from consolidate import consolidate, has_file_changes
    from database import get_connection, init_db
    from api.services.price_gaps import detect_price_gaps, has_gaps

    init_db(DB_PATH)
    conn = get_connection()
    try:
        if has_file_changes(DOCUMENTS_DIR, conn):
            print("New/changed transaction files detected. Consolidating...")
            conn.close()
            consolidate(DOCUMENTS_DIR, DB_PATH, skip_if_unchanged=False)
            conn = get_connection()
        else:
            print("No file changes. Skipping consolidation.")
        gaps = detect_price_gaps(conn)
    finally:
        conn.close()

    if has_gaps(gaps):
        print(
            f"Price gaps detected: {len(gaps['missing'])} new, "
            f"{len(gaps['stale'])} stale. Starting background fetch..."
        )
        Thread(target=_background_price_fetch, daemon=True).start()
    else:
        print("Price data is current.")

    Thread(target=_live_price_loop, daemon=True).start()
    print("Live price refresh scheduled (every 15 min).")

    yield


app = FastAPI(title="Portfolio Tracker API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(portfolio.router, prefix="/api", tags=["portfolio"])


@app.get("/health")
def health():
    return {"status": "ok"}

