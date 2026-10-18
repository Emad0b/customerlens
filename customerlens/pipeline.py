import hashlib
import json
import sqlite3
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import (
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
)
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    mean_absolute_error,
    roc_auc_score,
)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

FEATURES = [
    "recency",
    "frequency",
    "net_spend",
    "gross_spend",
    "basket_value",
    "products",
    "credit_share",
    "active_days",
]


def clean(raw):
    required = {
        "InvoiceNo",
        "StockCode",
        "Quantity",
        "InvoiceDate",
        "UnitPrice",
        "CustomerID",
        "Country",
    }
    if not required.issubset(raw):
        raise ValueError("Missing required transaction columns")
    frame = raw.drop_duplicates().copy()
    audit = {
        "raw_rows": len(raw),
        "duplicate_rows": len(raw) - len(frame),
        "missing_customer_rows": int(frame.CustomerID.isna().sum()),
    }
    frame = frame.dropna(subset=["CustomerID", "InvoiceDate", "Quantity", "UnitPrice"])
    frame["InvoiceDate"] = pd.to_datetime(frame.InvoiceDate, errors="raise")
    frame["Quantity"] = pd.to_numeric(frame.Quantity, errors="raise")
    frame["UnitPrice"] = pd.to_numeric(frame.UnitPrice, errors="raise")
    if not np.isfinite(frame.Quantity).all() or not np.isfinite(frame.UnitPrice).all():
        raise ValueError("Nonfinite transaction values")
    audit["nonpositive_price_rows"] = int((frame.UnitPrice <= 0).sum())
    frame = frame[(frame.UnitPrice > 0) & (frame.Quantity != 0)].copy()
    frame["CustomerID"] = frame.CustomerID.astype(int).astype(str)
    frame["InvoiceNo"] = frame.InvoiceNo.astype(str)
    frame["credit"] = frame.InvoiceNo.str.upper().str.startswith("C") | (
        frame.Quantity < 0
    )
    frame["value"] = np.where(
        frame.credit,
        -frame.Quantity.abs() * frame.UnitPrice,
        frame.Quantity * frame.UnitPrice,
    )
    frame["purchase"] = ~frame.credit & (frame.Quantity > 0)
    end = frame.InvoiceDate.max().normalize()
    audit["partial_last_day_rows"] = int((frame.InvoiceDate >= end).sum())
    frame = frame[frame.InvoiceDate < end].copy()
    audit.update(
        clean_rows=len(frame),
        credit_rows=int(frame.credit.sum()),
        customers=int(frame.CustomerID.nunique()),
        start=str(frame.InvoiceDate.min().date()),
        end_exclusive=str(end.date()),
        gross_sales=float(frame.loc[frame.purchase, "value"].sum()),
        credits=float(-frame.loc[frame.credit, "value"].sum()),
    )
    return frame.sort_values("InvoiceDate"), audit, end


def snapshot(frame, cutoff, days=90):
    cutoff = pd.Timestamp(cutoff)
    past = frame[
        (frame.InvoiceDate >= cutoff - pd.Timedelta(days=days))
        & (frame.InvoiceDate < cutoff)
    ]
    purchases = past[past.purchase]
    grouped = purchases.groupby("CustomerID")
    result = grouped.agg(
        last=("InvoiceDate", "max"),
        frequency=("InvoiceNo", "nunique"),
        gross_spend=("value", "sum"),
        products=("StockCode", "nunique"),
    )
    result["recency"] = (cutoff - result["last"]).dt.total_seconds() / 86400
    result["net_spend"] = (
        past.groupby("CustomerID").value.sum().reindex(result.index, fill_value=0)
    )
    credits = -past[past.credit].groupby("CustomerID").value.sum()
    result["credit_share"] = credits.reindex(
        result.index, fill_value=0
    ) / result.gross_spend.clip(lower=1)
    result["basket_value"] = result.gross_spend / result.frequency
    result["active_days"] = (
        purchases.assign(day=purchases.InvoiceDate.dt.normalize())
        .groupby("CustomerID")
        .day.nunique()
    )
    result["country"] = grouped.Country.agg(
        lambda values: values.mode().iloc[0] if len(values.mode()) else "Unknown"
    )
    future = frame[
        (frame.InvoiceDate >= cutoff)
        & (frame.InvoiceDate < cutoff + pd.Timedelta(days=days))
    ]
    repeat = future[future.purchase].groupby("CustomerID").size()
    result["repeat"] = result.index.isin(repeat.index).astype(int)
    result["future_net"] = (
        future.groupby("CustomerID").value.sum().reindex(result.index, fill_value=0)
    )
    return result


def classification_metrics(y, p):
    y = np.asarray(y)
    p = np.asarray(p)
    k = max(1, int(np.ceil(len(y) * 0.2)))
    top = np.argsort(-p, kind="stable")[:k]
    precision = float(y[top].mean())
    rate = float(y.mean())
    return {
        "roc_auc": float(roc_auc_score(y, p)) if len(np.unique(y)) > 1 else None,
        "average_precision": float(average_precision_score(y, p)),
        "brier": float(brier_score_loss(y, p)),
        "precision20": precision,
        "lift20": precision / rate if rate else None,
        "base_rate": rate,
        "customers": len(y),
    }


def segment(recency, frequency, spend, threshold):
    if recency <= 30 and frequency >= 2 and spend >= threshold:
        return "Champions"
    if recency > 60:
        return "Cooling"
    if frequency >= 3:
        return "Loyal"
    return "Occasional"


def run():
    manifest = json.loads(Path("data/source.json").read_text())
    source = Path("data/online_retail.xlsx")
    if hashlib.sha256(source.read_bytes()).hexdigest() != manifest["sha256"]:
        raise ValueError("Source fingerprint mismatch")
    Path("runtime").mkdir(exist_ok=True)
    cache = Path("runtime") / ("transactions-" + manifest["sha256"][:16] + ".pkl")
    raw = (
        pd.read_pickle(cache)
        if cache.exists()
        else pd.read_excel(source, engine="openpyxl")
    )
    if not cache.exists():
        raw.to_pickle(cache)
    frame, audit, end = clean(raw)
    cutoffs = [end - pd.Timedelta(days=i) for i in [270, 180, 90]]
    train, validation, test = [snapshot(frame, c) for c in cutoffs]
    candidates = {
        "prevalence": DummyClassifier(strategy="prior"),
        "logistic": make_pipeline(
            StandardScaler(), LogisticRegression(max_iter=1000, C=0.3, random_state=17)
        ),
        "boosting": HistGradientBoostingClassifier(
            max_iter=100, max_leaf_nodes=12, l2_regularization=10, random_state=17
        ),
    }
    predictions = {}
    scores = []
    for name, model in candidates.items():
        model.fit(train[FEATURES], train["repeat"])
        val = model.predict_proba(validation[FEATURES])[:, 1]
        pred = model.predict_proba(test[FEATURES])[:, 1]
        predictions[name] = pred
        scores.append(
            {
                "id": name,
                "label": {
                    "prevalence": "Prevalence baseline",
                    "logistic": "Logistic regression",
                    "boosting": "Gradient boosting",
                }[name],
                "validation": classification_metrics(validation["repeat"], val),
                "test": classification_metrics(test["repeat"], pred),
            }
        )
    selected = min(scores, key=lambda row: row["validation"]["brier"])["id"]
    regressor = HistGradientBoostingRegressor(
        loss="absolute_error",
        max_iter=100,
        max_leaf_nodes=12,
        l2_regularization=10,
        random_state=17,
    )
    regressor.fit(train[FEATURES], train["future_net"])
    revenue_candidates = {
        "trailing": (validation.net_spend.to_numpy(), test.net_spend.to_numpy()),
        "mean": (
            np.repeat(train.future_net.mean(), len(validation)),
            np.repeat(train.future_net.mean(), len(test)),
        ),
        "boosting": (
            regressor.predict(validation[FEATURES]),
            regressor.predict(test[FEATURES]),
        ),
    }
    revenue_scores = [
        {
            "id": name,
            "label": {
                "trailing": "Trailing 90-day net spend",
                "mean": "Training-cohort mean",
                "boosting": "Robust gradient boosting",
            }[name],
            "validation_mae": float(
                mean_absolute_error(validation.future_net, values[0])
            ),
            "test_mae": float(mean_absolute_error(test.future_net, values[1])),
        }
        for name, values in revenue_candidates.items()
    ]
    selected_revenue = min(revenue_scores, key=lambda row: row["validation_mae"])["id"]
    threshold = float(train.net_spend.quantile(0.75))
    customers = []
    for i, (key, row) in enumerate(test.iterrows()):
        customers.append(
            {
                "id": "CL-" + hashlib.sha256(key.encode()).hexdigest()[:10].upper(),
                "recency": round(float(row.recency), 1),
                "orders": int(row.frequency),
                "net_spend": round(float(row.net_spend), 2),
                "gross_spend": round(float(row.gross_spend), 2),
                "credit_share": round(float(row.credit_share), 4),
                "country": str(row.country),
                "segment": segment(
                    row.recency, row.frequency, row.net_spend, threshold
                ),
                "probability": {
                    name: round(float(p[i]), 6) for name, p in predictions.items()
                },
                "expected_net": {
                    name: round(float(v[1][i]), 2)
                    for name, v in revenue_candidates.items()
                },
                "actual_repeat": int(row["repeat"]),
                "actual_net": round(float(row.future_net), 2),
            }
        )
    calibration = []
    for name, p in predictions.items():
        for lo in np.arange(0, 1, 0.1):
            mask = (p >= lo) & (p < (lo + 0.1) if lo < 0.89 else p <= 1)
            if mask.any():
                calibration.append(
                    {
                        "model": name,
                        "bin": round(float(lo), 1),
                        "predicted": float(p[mask].mean()),
                        "observed": float(test["repeat"].to_numpy()[mask].mean()),
                        "customers": int(mask.sum()),
                    }
                )
    ranked = sorted(customers, key=lambda r: -r["probability"][selected])
    spend_ranked = sorted(customers, key=lambda r: -r["net_spend"])
    targeting = []
    for fraction in [10, 20, 30, 50, 100]:
        k = max(1, int(np.ceil(len(customers) * fraction / 100)))
        targeting.append(
            {
                "fraction": fraction,
                "customers": k,
                "model_repeat_rate": float(
                    np.mean([r["actual_repeat"] for r in ranked[:k]])
                ),
                "spend_repeat_rate": float(
                    np.mean([r["actual_repeat"] for r in spend_ranked[:k]])
                ),
                "model_net": float(sum(r["actual_net"] for r in ranked[:k])),
                "spend_net": float(sum(r["actual_net"] for r in spend_ranked[:k])),
            }
        )
    cohort = purchases = frame[frame.purchase].copy()
    cohort["month"] = cohort.InvoiceDate.dt.to_period("M").astype(str)
    first = cohort.groupby("CustomerID").month.min()
    cohort["cohort"] = cohort.CustomerID.map(first)
    cohort["offset"] = (
        cohort.month.str[:4].astype(int) - cohort.cohort.str[:4].astype(int)
    ) * 12 + (cohort.month.str[5:].astype(int) - cohort.cohort.str[5:].astype(int))
    cohorts = []
    for key, group in cohort.groupby("cohort"):
        # The last partial calendar month is excluded, not filled with false zeros.
        complete = group[group["month"] < str(end.to_period("M"))]
        if complete.empty:
            continue
        counts = complete.groupby("offset").CustomerID.nunique()
        initial = int(first.eq(key).sum())
        last_complete = end.to_period("M") - 1
        max_offset = (
            (last_complete.year - int(key[:4])) * 12
            + last_complete.month
            - int(key[5:])
        )
        counts = counts.reindex(range(max_offset + 1), fill_value=0)
        cohorts.append(
            {
                "cohort": key,
                "customers": initial,
                "retention": {
                    str(int(k)): float(v / initial) for k, v in counts.items()
                },
            }
        )
    monthly = (
        frame.assign(month=frame.InvoiceDate.dt.to_period("M").astype(str))
        .groupby("month")
        .agg(
            net=("value", "sum"),
            customers=("CustomerID", "nunique"),
            rows=("value", "size"),
        )
        .reset_index()
        .to_dict("records")
    )
    with sqlite3.connect("runtime/customerlens.sqlite") as connection:
        frame[
            ["CustomerID", "InvoiceNo", "InvoiceDate", "value", "purchase", "credit"]
        ].to_sql("transactions", connection, index=False, if_exists="replace")
    payload = {
        "source": {**manifest, **audit},
        "protocol": {
            "lookback_days": 90,
            "outcome_days": 90,
            "train_cutoff": str(cutoffs[0].date()),
            "validation_cutoff": str(cutoffs[1].date()),
            "test_cutoff": str(cutoffs[2].date()),
            "end_exclusive": str(end.date()),
            "train_customers": len(train),
            "validation_customers": len(validation),
            "test_customers": len(test),
            "segment_spend_threshold": threshold,
        },
        "selected_model": selected,
        "selected_revenue": selected_revenue,
        "scores": scores,
        "revenue_scores": revenue_scores,
        "customers": customers,
        "calibration": calibration,
        "targeting": targeting,
        "cohorts": cohorts,
        "monthly": monthly,
    }
    Path("public/benchmark.json").write_text(
        json.dumps(payload, separators=(",", ":"), allow_nan=False), encoding="utf-8"
    )
    Path("docs/metrics.json").write_text(
        json.dumps(
            {
                k: v
                for k, v in payload.items()
                if k not in ["customers", "cohorts", "monthly"]
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "audit": audit,
                "protocol": payload["protocol"],
                "selected": selected,
                "scores": scores,
                "selected_revenue": selected_revenue,
                "revenue_scores": revenue_scores,
            },
            indent=2,
        ),
        flush=True,
    )
    return payload


if __name__ == "__main__":
    run()
