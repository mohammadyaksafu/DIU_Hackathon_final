"""Feature registry: one place that assembles the full feature vector.

Extension point (plan section 9.1): to add a feature during the on-site round, write

    @feature("my_new_feature")
    def my_new_feature(f: dict, tx: dict) -> float:
        return ...

It is computed for training and serving alike; retrain to let the model use it.
"""
from __future__ import annotations

from typing import Callable

from app.features.engine import AGENT_FEATURES, CASH_OUT_LIMIT, STREAM_FEATURES, FeatureEngine
from app.graph.snapshot import GRAPH_FEATURES, graph_features_for

DerivedFn = Callable[[dict, dict], float]
_DERIVED: dict[str, DerivedFn] = {}

# Registered merchant / online-seller profiles (onboarded business wallets). Many new payers are
# normal for them, so the mule-network signals are merchant-aware. Set at boot and in the pipeline.
MERCHANT_PROFILES: set[str] = set()
MERCHANT_PERSONAS = ("shopkeeper", "fcommerce_seller")


def set_merchant_profiles(wallet_ids) -> None:
    MERCHANT_PROFILES.clear()
    MERCHANT_PROFILES.update(wallet_ids)


def feature(name: str):
    def deco(fn: DerivedFn) -> DerivedFn:
        _DERIVED[name] = fn
        return fn

    return deco


@feature("amount_to_limit")
def _amount_to_limit(f: dict, tx: dict) -> float:
    return round(f["amount"] / CASH_OUT_LIMIT, 4)


@feature("recent_device")
def _recent_device(f: dict, tx: dict) -> float:
    """1 if the phone is new to this wallet, or was first used on it within 24h."""
    return float(f["is_new_device"] == 1 or (f["s_device_age_hrs"] < 24 and f["s_device_count"] >= 2))


@feature("night_new_recipient")
def _night_new_recipient(f: dict, tx: dict) -> float:
    return float(f["is_night"] * f["is_new_recipient"])


@feature("new_device_new_recipient")
def _new_device_new_recipient(f: dict, tx: dict) -> float:
    return float(_recent_device(f, tx) * f["is_new_recipient"])


@feature("r_merchant_profile")
def _r_merchant_profile(f: dict, tx: dict) -> float:
    return float(tx["receiver"] in MERCHANT_PROFILES)


@feature("s_merchant_profile")
def _s_merchant_profile(f: dict, tx: dict) -> float:
    return float(tx["sender"] in MERCHANT_PROFILES)


@feature("on_call")
def _on_call(f: dict, tx: dict) -> float:
    """The app reports an active phone call while the transfer is made (a social-engineering signal)."""
    return float(bool(tx.get("on_call")))


# Computed (for rules/explanations/detectors) but not used as model inputs: raw clock hour is a
# dataset artefact; profiles, call state and agent counters drive rules and detectors instead,
# so they can change without retraining the model.
NON_MODEL_FEATURES = {"hour", "r_merchant_profile", "s_merchant_profile", "on_call", *AGENT_FEATURES}


def all_feature_names() -> list[str]:
    return STREAM_FEATURES + AGENT_FEATURES + GRAPH_FEATURES + list(_DERIVED)


def model_feature_names() -> list[str]:
    return [f for f in all_feature_names() if f not in NON_MODEL_FEATURES]


def build_features(engine: FeatureEngine, tx: dict, snapshot: dict) -> dict:
    f = engine.compute(tx)
    f.update(graph_features_for(snapshot, tx["sender"], tx["receiver"]))
    for name, fn in _DERIVED.items():
        f[name] = fn(f, tx)
    return f
