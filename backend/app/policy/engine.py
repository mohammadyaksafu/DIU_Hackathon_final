"""Hot-reloadable decision policy (config/policy.yaml).

Business rules live here, separate from ML predictions (guideline section 12):
detectors produce calibrated scores; the policy turns scores into an action.
"""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.policy.expr import compile_expr, evaluate

logger = logging.getLogger(__name__)

ACTIONS = ("ALLOW", "WARN", "HOLD")
MODES = ("shadow", "warn", "enforce")
_DEFAULT_THRESHOLDS = {"warn_t": 0.5, "hold_t": 0.9}


@dataclass
class Decision:
    action: str
    tier_expr: str
    variables: dict
    overrides_applied: list = field(default_factory=list)


class PolicyEngine:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._mtime: float | None = None
        self.config: dict = {}
        self.model_thresholds: dict = dict(_DEFAULT_THRESHOLDS)
        self.load()

    @property
    def version(self) -> int:
        return int(self.config.get("version", 0))

    @property
    def mode(self) -> str:
        return str(self.config.get("mode", "enforce"))

    @property
    def on_scoring_error(self) -> str:
        return str(self.config.get("on_scoring_error", "WARN"))

    def apply_mode(self, action: str) -> str:
        """What the customer sees, given the rollout mode. Alerts always record the policy decision."""
        if self.mode == "shadow":
            return "ALLOW"
        if self.mode == "warn" and action == "HOLD":
            return "WARN"
        return action

    def load(self) -> dict:
        with open(self.path, encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh) or {}
        # Validate before swapping in: a broken edit never replaces a working policy.
        for tier in cfg.get("tiers", []):
            if tier.get("action") not in ACTIONS:
                raise ValueError(f"Unknown action {tier.get('action')!r}")
            compile_expr(str(tier["when"]))
        for ov in cfg.get("segment_overrides", []):
            compile_expr(str(ov["when"]))
        if not cfg.get("tiers"):
            raise ValueError("policy has no tiers")
        if cfg.get("mode", "enforce") not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        if cfg.get("on_scoring_error", "WARN") not in ("ALLOW", "WARN"):
            raise ValueError("on_scoring_error must be ALLOW or WARN")
        with self._lock:
            self.config = cfg
            self._mtime = os.path.getmtime(self.path)
        logger.info("policy loaded", extra={"extra_fields": {"version": cfg.get("version")}})
        return cfg

    def maybe_reload(self) -> None:
        """Cheap mtime check on each request => edits are live without restart."""
        try:
            mtime = os.path.getmtime(self.path)
        except OSError:
            return
        if self._mtime is None or mtime > self._mtime:
            try:
                self.load()
            except Exception as exc:
                logger.error("policy reload failed; keeping previous policy: %s", exc)
                self._mtime = mtime

    def set_model_thresholds(self, thresholds: dict) -> None:
        self.model_thresholds = {**_DEFAULT_THRESHOLDS, **{k: v for k, v in thresholds.items() if v is not None}}

    def resolve_variables(self, names: dict) -> tuple[dict, list]:
        variables: dict = {}
        for key, value in (self.config.get("variables") or {}).items():
            variables[key] = self.model_thresholds.get(key, 0.5) if value == "model" else value
        applied = []
        for ov in self.config.get("segment_overrides") or []:
            if evaluate(str(ov["when"]), {**names, **variables}):
                name = ov.get("name", ov["when"])
                if ov.get("shadow"):  # logged for validation, not applied (segment rules are validated before enforcing)
                    applied.append(f"{name} (shadow)")
                    continue
                for key, value in (ov.get("set") or {}).items():
                    variables[key] = evaluate(value, {**names, **variables}) if isinstance(value, str) else value
                applied.append(name)
        return variables, applied

    def decide(self, names: dict, rule_hits: set[str]) -> Decision:
        self.maybe_reload()
        variables, applied = self.resolve_variables(names)
        scope = {**names, **variables}
        funcs = {"rule_hit": lambda name: name in rule_hits}
        for tier in self.config["tiers"]:
            if evaluate(str(tier["when"]), scope, funcs):
                return Decision(tier["action"], str(tier["when"]), variables, applied)
        return Decision("ALLOW", "default", variables, applied)
