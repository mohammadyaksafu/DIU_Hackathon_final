"""Process-wide application state: models, detectors, policy, feature engine, graph.

Boot order (each step degrades gracefully instead of crashing the API):
  1. Bootstrap data + model if missing (AUTO_BOOTSTRAP)
  2. Load the active model bundle    -> on failure: rules-only mode
  3. Load the warm online state      -> on failure: cold engine (features still computed)
     and share it through Redis when REDIS_URL is set -> on failure: this worker keeps it in memory
  4. Build detectors + policy
  5. Seed analyst alerts (SEED_ON_BOOT)
  6. Start the background graph refresher (cold path)
"""
from __future__ import annotations

import json
import logging
import pickle
import threading
import time
from pathlib import Path

import pandas as pd

from app.core.config import Settings, get_settings
from app.detectors.base import DetectorDeps
from app.detectors.registry import DetectorRegistry
from app.features.engine import FeatureEngine
from app.features.registry import MERCHANT_PERSONAS, set_merchant_profiles
from app.graph.store import GraphStore
from app.policy.engine import PolicyEngine
from app.services import model_registry

logger = logging.getLogger(__name__)


class AppState:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.lock = threading.RLock()
        self.bundle: model_registry.ModelBundle | None = None
        self.engine = FeatureEngine()
        self.graph = GraphStore()
        self.policy = PolicyEngine(settings.config_dir / "policy.yaml")
        self.detectors: DetectorRegistry | None = None
        self.data_meta: dict = {}
        self.customers: pd.DataFrame | None = None
        self.boot_wall = time.time()
        self.sim_origin = 0.0
        self.degraded: list[str] = []
        self.shared_state = False  # online state lives in Redis (several workers, survives restarts)
        self._model_checked = 0.0
        self._stop = threading.Event()
        self._refresher: threading.Thread | None = None

    # ------------------------------------------------------------------ boot
    def boot(self) -> None:
        s = self.settings
        if s.auto_bootstrap and model_registry.active_version(s.models_dir, s.active_model) is None:
            logger.warning("no trained model found; running bootstrap pipeline (one-time)")
            from pipelines.run_all import run

            run(s.data_dir, s.models_dir, s.config_dir, s.data_dir.parent / "reports", verbose=False)
        self.load_model(s.active_model)
        self.load_online_state()
        self.share_online_state()
        meta_path = s.data_dir / "raw" / "meta.json"
        if meta_path.exists():
            self.data_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        cust_path = s.data_dir / "raw" / "customers.parquet"
        if cust_path.exists():
            self.customers = pd.read_parquet(cust_path).set_index("id")
            set_merchant_profiles(self.customers.index[self.customers.persona.isin(MERCHANT_PERSONAS)])
        # Simulation clock continues after the synthetic history, aligned to the real
        # Dhaka time of day so a demo at 3 pm is scored as 3 pm.
        end = max(self.engine.last_ts, float(self.data_meta.get("end_ts", time.time())))
        day_start = end - ((end + 6 * 3600) % 86400)
        tod = (time.time() + 6 * 3600) % 86400
        self.sim_origin = day_start + tod if day_start + tod > end else day_start + 86400 + tod
        self.boot_wall = time.time()

    def load_model(self, version: str = "") -> None:
        s = self.settings
        self.degraded = [d for d in self.degraded if d != "model"]
        try:
            v = model_registry.active_version(s.models_dir, version)
            if v is None:
                raise RuntimeError("no model in registry")
            self.bundle = model_registry.load_bundle(s.models_dir, v)
            self.policy.set_model_thresholds(self.bundle.thresholds)
        except Exception as exc:
            logger.error("model load failed, running rules-only: %s", exc)
            self.bundle = None
            self.degraded.append("model")
        self.detectors = DetectorRegistry(s.config_dir / "detectors.yaml", DetectorDeps(self.bundle, s.config_dir))

    def load_online_state(self) -> None:
        path = self.settings.data_dir / "online_state.pkl"
        try:
            with open(path, "rb") as fh:
                state = pickle.load(fh)
            self.engine = state["engine"]
            self.graph = GraphStore()
            for ts, src, dst, amount, ttype in state["graph_edges"]:
                self.graph.edges.append((ts, src, dst, amount, ttype))
            self.graph.refresh()
        except Exception as exc:
            logger.error("online state unavailable, starting cold: %s", exc)
            self.degraded.append("online_state")

    def share_online_state(self) -> None:
        """Move the online state into Redis so every API worker reads and writes the same history."""
        s = self.settings
        if s.feature_store == "memory" or not s.redis_url:
            if s.feature_store == "redis":
                self.degraded.append("shared_state")
            return
        from app.features import store

        try:
            client = store.connect(s.redis_url)
            fingerprint = f"{self.bundle.version if self.bundle else 'none'}:{self.engine.last_ts}"
            with client.lock(store.PREFIX + "seed-lock", timeout=300, blocking_timeout=300):
                store.seed(client, self.engine.wallets, fingerprint)
            self.engine.wallets = store.RedisWalletStore(client)
            self.graph.shared = store.SharedEdges(client)
            self.graph.refresh()
            self.shared_state = True
        except Exception as exc:
            logger.error("redis online state unavailable, keeping it in this worker's memory: %s", exc)
            if s.feature_store == "redis":
                self.degraded.append("shared_state")

    def sync_model(self) -> None:
        """Follow model activations made through another worker (the ACTIVE file is shared)."""
        now = time.monotonic()
        if self.settings.active_model or now - self._model_checked < 5:
            return
        self._model_checked = now
        version = model_registry.active_version(self.settings.models_dir)
        if version and self.bundle is not None and version != self.bundle.version:
            self.load_model(version)

    # ------------------------------------------------------------ simulation
    def sim_now(self) -> float:
        """Simulation clock: continues from the end of the synthetic history."""
        return self.sim_origin + (time.time() - self.boot_wall)

    # ------------------------------------------------------- graph refresher
    def start_background(self) -> None:
        if self._refresher is not None:
            return

        def loop() -> None:
            while not self._stop.wait(self.settings.graph_refresh_seconds):
                try:
                    started = time.time()
                    self.graph.refresh()
                    logger.info("graph snapshot refreshed", extra={"extra_fields": {"seconds": round(time.time() - started, 2)}})
                except Exception:
                    logger.exception("graph refresh failed")

        self._refresher = threading.Thread(target=loop, name="graph-refresher", daemon=True)
        self._refresher.start()

    def stop(self) -> None:
        self._stop.set()

    def customer_profile(self, wallet: str) -> dict:
        if self.customers is None or wallet not in self.customers.index:
            return {}
        row = self.customers.loc[wallet]
        return {
            "id": wallet,
            "name": row["name"],
            "persona": row["persona"],
            "division": row["division"],
            "age_band": row["age_band"],
            "kyc_level": int(row["kyc_level"]),
            "is_synthetic": True,
        }


_state: AppState | None = None


def get_state() -> AppState:
    global _state
    if _state is None:
        _state = AppState(get_settings())
    return _state


def reset_state() -> None:
    global _state
    if _state is not None:
        _state.stop()
    _state = None
