"""Lazy API session stores; transient requests have no native store."""
import asyncio
import logging

from gateway.platforms.api_server_profile_writer import run_profile_thread

logger = logging.getLogger("gateway.platforms.api_server")

def _ensure_session_db(self):
    """SessionDB for the active profile home (the runtime scope redirects ``get_hermes_home()``
    per profile). Sync, for ``_create_agent``; handlers use ``_ensure_session_db_async``."""
    if self._transient_sessions:
        return None
    if self._session_db is not None:
        return self._session_db
    try:
        from hermes_constants import get_hermes_home
        return self._open_and_cache_session_db(get_hermes_home())
    except Exception as e:
        logger.debug("SessionDB unavailable for API server: %s", e, exc_info=True)
        return None

async def _ensure_session_db_async(self):
    """Async variant: the profile home is captured on the loop thread (its scope is invisible
    inside ``to_thread``), only the blocking open runs in the worker, single-flight locked."""
    if self._transient_sessions:
        return None
    if self._session_db is not None:
        return self._session_db
    try:
        from hermes_constants import get_hermes_home
        home = get_hermes_home()
        key = str(home)
        with self._session_db_cache_lock:
            cached = self._cached_session_db_locked(key)
        if cached is not None:
            return cached
        if self._session_db_lock is None:
            self._session_db_lock = asyncio.Lock()
        async with self._session_db_lock:
            with self._session_db_cache_lock:
                cached = self._cached_session_db_locked(key)
            if cached is not None:
                return cached
            return await run_profile_thread(self._open_and_cache_session_db, home)
    except Exception as e:
        logger.debug("SessionDB unavailable for API server: %s", e, exc_info=True)
        return None

