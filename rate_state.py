"""Circuit breaker adaptatif persistant pour eviter les rate-limits Similarweb.

Trois etats logiques:
- CLOSED : cadence nominale, multiplier = 1.0
- HALF_OPEN : multiplier > 1.0 (on ralentit apres un 403/429 ponctuel)
- OPEN : hard_cooldown_until > now (on bloque tout depart)

L'etat est persiste dans la meme DB SQLite que le cache pour survivre aux re-runs
Streamlit (le script est re-execute a chaque interaction utilisateur).

Le 403 CloudFront renvoye par `data.similarweb.com` est traite comme un blocage
global probable: le batch est coupe immediatement et un cooldown long est persiste.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Deque, Optional

from config import DEFAULT_LONG_COOLDOWN_SECONDS, get_logger

logger = get_logger("rate_state")

# Escalade du hard cooldown selon le nombre de blocages consecutifs.
COOLDOWN_SCHEDULE_SECONDS = {
    1: DEFAULT_LONG_COOLDOWN_SECONDS,       # 1 h par defaut apres un 403 CloudFront
    2: DEFAULT_LONG_COOLDOWN_SECONDS * 2,   # 2 h si le blocage revient vite
    3: DEFAULT_LONG_COOLDOWN_SECONDS * 4,   # 4 h apres repetitions
}
DEFAULT_COOLDOWN_SECONDS = DEFAULT_LONG_COOLDOWN_SECONDS
MAX_DELAY_MULTIPLIER = 8.0
MIN_DELAY_MULTIPLIER = 1.0
WINDOW_SIZE = 10
GLOBAL_RATE_LIMIT_THRESHOLD = 0.3  # >= 30 % de 403 dans la fenetre = "global"

# Seuil d'abandon d'un batch: un seul 403 global suffit.
BATCH_ABORT_THRESHOLD = 1


@dataclass
class RateLimitSnapshot:
    consecutive_403: int = 0
    consecutive_429: int = 0
    last_block_at: float = 0.0
    current_delay_multiplier: float = 1.0
    hard_cooldown_until: float = 0.0
    updated_at: float = 0.0

    @property
    def state(self) -> str:
        now = time.time()
        if self.hard_cooldown_until > now:
            return "OPEN"
        if self.consecutive_403 or self.consecutive_429 or self.current_delay_multiplier > 1.01:
            return "HALF_OPEN"
        return "CLOSED"


@dataclass
class _InternalState:
    consecutive_403: int = 0
    consecutive_429: int = 0
    last_block_at: float = 0.0
    current_delay_multiplier: float = 1.0
    hard_cooldown_until: float = 0.0
    updated_at: float = 0.0
    # La fenetre glissante n'est pas persistee (pertinente seulement au sein d'une session process).
    recent_outcomes: Deque[bool] = field(default_factory=lambda: deque(maxlen=WINDOW_SIZE))


class RateLimitController:
    """Singleton par process, thread-safe, persiste en SQLite."""

    _instance: "Optional[RateLimitController]" = None
    _instance_lock = threading.Lock()

    def __init__(self, db_path: str = "similarweb_cache.db"):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._state = _InternalState()
        self._ensure_table()
        self._load()

    # ---- construction singleton ----
    @classmethod
    def get_instance(cls, db_path: str = "similarweb_cache.db") -> "RateLimitController":
        with cls._instance_lock:
            if cls._instance is None or cls._instance.db_path != db_path:
                cls._instance = cls(db_path)
            return cls._instance

    # ---- persistence ----
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _ensure_table(self) -> None:
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS rate_state (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        consecutive_403 INTEGER,
                        consecutive_429 INTEGER,
                        last_block_at REAL,
                        current_delay_multiplier REAL,
                        hard_cooldown_until REAL,
                        updated_at REAL
                    )
                    """
                )
                conn.commit()
        except sqlite3.Error:
            logger.exception("rate_state table bootstrap failed")

    def _load(self) -> None:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT consecutive_403, consecutive_429, last_block_at, "
                    "current_delay_multiplier, hard_cooldown_until, updated_at "
                    "FROM rate_state WHERE id = 1"
                ).fetchone()
        except sqlite3.Error:
            logger.exception("rate_state load failed, starting fresh")
            return

        if not row:
            return

        (c403, c429, last_block, multiplier, cooldown_until, updated_at) = row

        # Garde-fou: si la derniere mise a jour date de > 24h, repart d'un etat propre.
        if updated_at and time.time() - updated_at > 86400:
            logger.info("rate_state older than 24h, resetting")
            return

        with self._lock:
            self._state.consecutive_403 = int(c403 or 0)
            self._state.consecutive_429 = int(c429 or 0)
            self._state.last_block_at = float(last_block or 0.0)
            self._state.current_delay_multiplier = max(
                MIN_DELAY_MULTIPLIER,
                min(MAX_DELAY_MULTIPLIER, float(multiplier or 1.0)),
            )
            self._state.hard_cooldown_until = float(cooldown_until or 0.0)
            self._state.updated_at = float(updated_at or 0.0)

    def _persist_locked(self) -> None:
        # Appele sous self._lock.
        self._state.updated_at = time.time()
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO rate_state (id, consecutive_403, consecutive_429,
                        last_block_at, current_delay_multiplier, hard_cooldown_until, updated_at)
                    VALUES (1, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        consecutive_403 = excluded.consecutive_403,
                        consecutive_429 = excluded.consecutive_429,
                        last_block_at = excluded.last_block_at,
                        current_delay_multiplier = excluded.current_delay_multiplier,
                        hard_cooldown_until = excluded.hard_cooldown_until,
                        updated_at = excluded.updated_at
                    """,
                    (
                        self._state.consecutive_403,
                        self._state.consecutive_429,
                        self._state.last_block_at,
                        self._state.current_delay_multiplier,
                        self._state.hard_cooldown_until,
                        self._state.updated_at,
                    ),
                )
                conn.commit()
        except sqlite3.Error:
            logger.exception("rate_state persist failed")

    # ---- API publique ----
    def before_request(self) -> float:
        """Temps d'attente additionnel (en secondes) avant de pouvoir emettre une requete."""
        now = time.time()
        with self._lock:
            remaining = self._state.hard_cooldown_until - now
            return remaining if remaining > 0 else 0.0

    def current_multiplier(self) -> float:
        with self._lock:
            return self._state.current_delay_multiplier

    def is_in_cooldown(self) -> bool:
        with self._lock:
            return self._state.hard_cooldown_until > time.time()

    def on_success(self) -> None:
        with self._lock:
            changed = False
            if self._state.consecutive_403 or self._state.consecutive_429:
                self._state.consecutive_403 = 0
                self._state.consecutive_429 = 0
                changed = True
            new_multiplier = max(MIN_DELAY_MULTIPLIER, self._state.current_delay_multiplier * 0.8)
            if abs(new_multiplier - self._state.current_delay_multiplier) > 0.01:
                self._state.current_delay_multiplier = new_multiplier
                changed = True
            self._state.recent_outcomes.append(True)  # True = success
            if changed:
                self._persist_locked()

    def on_rate_limit(self, status_code: int, provider_blocked: bool = False) -> None:
        with self._lock:
            now = time.time()
            self._state.last_block_at = now
            self._state.recent_outcomes.append(False)  # False = blocked

            if status_code == 403:
                self._state.consecutive_403 += 1
                self._state.current_delay_multiplier = min(
                    MAX_DELAY_MULTIPLIER,
                    self._state.current_delay_multiplier * 2.0,
                )
            else:  # 429 ou autre
                self._state.consecutive_429 += 1
                self._state.current_delay_multiplier = min(
                    MAX_DELAY_MULTIPLIER,
                    self._state.current_delay_multiplier * 1.5,
                )

            # Seul un blocage provider/CDN confirme doit ouvrir un hard cooldown.
            # Un 403 ponctuel peut etre un refus par domaine ou session et doit
            # rester retryable, sinon le batch devient instable apres un seul hit.
            block_ratio = self._compute_block_ratio_locked()
            should_cooldown = (
                provider_blocked
                or (
                    self._state.consecutive_429 >= BATCH_ABORT_THRESHOLD + 1
                    and block_ratio >= GLOBAL_RATE_LIMIT_THRESHOLD
                )
            )
            if should_cooldown:
                consecutive_blocks = max(self._state.consecutive_403, self._state.consecutive_429)
                cooldown = COOLDOWN_SCHEDULE_SECONDS.get(
                    consecutive_blocks, DEFAULT_COOLDOWN_SECONDS
                )
                self._state.hard_cooldown_until = now + cooldown
                logger.warning(
                    "Hard cooldown triggered: %ds (consecutive_403=%d, consecutive_429=%d, block_ratio=%.2f)",
                    cooldown, self._state.consecutive_403, self._state.consecutive_429, block_ratio,
                )

            self._persist_locked()

    def should_abort_batch(self) -> bool:
        with self._lock:
            if self._state.hard_cooldown_until > time.time():
                return True
            block_ratio = self._compute_block_ratio_locked()
            return (
                self._state.consecutive_429 >= BATCH_ABORT_THRESHOLD + 1
                and block_ratio >= GLOBAL_RATE_LIMIT_THRESHOLD
            )

    def _compute_block_ratio_locked(self) -> float:
        if not self._state.recent_outcomes:
            return 0.0
        blocked = sum(1 for outcome in self._state.recent_outcomes if not outcome)
        return blocked / len(self._state.recent_outcomes)

    def get_snapshot(self) -> RateLimitSnapshot:
        with self._lock:
            return RateLimitSnapshot(
                consecutive_403=self._state.consecutive_403,
                consecutive_429=self._state.consecutive_429,
                last_block_at=self._state.last_block_at,
                current_delay_multiplier=self._state.current_delay_multiplier,
                hard_cooldown_until=self._state.hard_cooldown_until,
                updated_at=self._state.updated_at,
            )

    def reset(self) -> None:
        """Pour tests/debug uniquement."""
        with self._lock:
            self._state = _InternalState()
            self._persist_locked()


def get_controller(db_path: str = "similarweb_cache.db") -> RateLimitController:
    """Accesseur pratique pour obtenir le singleton."""
    return RateLimitController.get_instance(db_path)
