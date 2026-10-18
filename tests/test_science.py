import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from customerlens.pipeline import (
    FEATURES,
    classification_metrics,
    clean,
    segment,
    snapshot,
)


def test_cleaning_preserves_signed_credits_and_excludes_invalid_rows():
    def row(invoice, day, quantity, customer=1, price=2):
        return {
            "InvoiceNo": invoice,
            "StockCode": "A",
            "Quantity": quantity,
            "InvoiceDate": day,
            "UnitPrice": price,
            "CustomerID": customer,
            "Country": "UK",
        }

    a = row("100", "2020-01-01", 10)
    data = pd.DataFrame(
        [
            a,
            a.copy(),
            row("C101", "2020-01-05", -2),
            row("102", "2020-01-06", 1, None),
            row("103", "2020-01-07", 1, 1, 0),
            row("999", "2020-01-10", 1, 99),
        ]
    )
    frame, audit, end = clean(data)
    assert (
        audit["duplicate_rows"]
        == audit["missing_customer_rows"]
        == audit["nonpositive_price_rows"]
        == 1
    )
    assert len(frame) == 2 and frame.value.sum() == 16
    assert audit["credits"] == 4 and frame.purchase.sum() == 1
    assert end == pd.Timestamp("2020-01-10")


def transactions():
    return pd.DataFrame(
        {
            "CustomerID": ["1", "1", "1", "2", "2"],
            "InvoiceNo": ["1", "2", "C3", "4", "5"],
            "InvoiceDate": pd.to_datetime(
                ["2020-01-03", "2020-04-01", "2020-04-02", "2020-02-01", "2020-03-31"]
            ),
            "StockCode": ["A"] * 5,
            "value": [100.0, 50.0, -20.0, 30.0, 40.0],
            "credit": [False, False, True, False, False],
            "purchase": [True, True, False, True, True],
            "Country": ["UK"] * 5,
        }
    )


def test_snapshot_excludes_future_features_and_retains_net_refunds():
    data = transactions()
    cutoff = pd.Timestamp("2020-04-01")
    original = snapshot(data, cutoff)
    assert original.loc["1", "net_spend"] == 100
    assert original.loc["1", "repeat"] == 1 and original.loc["1", "future_net"] == 30
    changed = data.copy()
    changed.loc[changed.InvoiceDate >= cutoff, "value"] *= 1000
    new = snapshot(changed, cutoff)
    pd.testing.assert_frame_equal(original[FEATURES], new[FEATURES])
    assert new.loc["1", "future_net"] != original.loc["1", "future_net"]


def test_credits_alone_are_not_repeat_purchases():
    data = transactions()
    data = data[~data.InvoiceNo.eq("2")]
    result = snapshot(data, pd.Timestamp("2020-04-01"))
    assert result.loc["1", "repeat"] == 0 and result.loc["1", "future_net"] == -20


def test_classification_metrics_are_not_accuracy_percentages():
    result = classification_metrics([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9])
    assert result["roc_auc"] == result["average_precision"] == 1
    assert result["brier"] == pytest.approx(0.025)
    assert result["precision20"] == 1 and result["lift20"] == 2


def test_segment_boundaries_are_explicit():
    assert segment(10, 4, 1000, 750) == "Champions"
    assert segment(70, 4, 1000, 750) == "Cooling"
    assert segment(45, 3, 500, 750) == "Loyal"
    assert segment(10, 1, 1000, 750) == "Occasional"


def test_artifact_has_disjoint_time_windows_and_past_only_features():
    data = json.loads(Path("public/benchmark.json").read_text())
    p = data["protocol"]
    times = [
        pd.Timestamp(p[k])
        for k in ["train_cutoff", "validation_cutoff", "test_cutoff", "end_exclusive"]
    ]
    assert all((b - a).days == 90 for a, b in zip(times, times[1:]))
    assert not {"CustomerID", "country", "repeat", "future_net"}.intersection(FEATURES)
    assert data["source"]["raw_rows"] == 541909
    assert len(data["customers"]) == p["test_customers"] == 1907
    assert len({r["id"] for r in data["customers"]}) == 1907


def test_model_selection_uses_validation_not_test():
    data = json.loads(Path("public/benchmark.json").read_text())
    assert (
        data["selected_model"]
        == min(data["scores"], key=lambda s: s["validation"]["brier"])["id"]
    )
    assert (
        data["selected_revenue"]
        == min(data["revenue_scores"], key=lambda s: s["validation_mae"])["id"]
    )
    # The selected revenue model loses to the trailing baseline on the later test.
    chosen = next(
        s for s in data["revenue_scores"] if s["id"] == data["selected_revenue"]
    )
    assert chosen["test_mae"] > min(s["test_mae"] for s in data["revenue_scores"])


def test_customer_probabilities_and_reported_metrics_agree():
    data = json.loads(Path("public/benchmark.json").read_text())
    customers = data["customers"]
    for score in data["scores"]:
        probabilities = np.array([r["probability"][score["id"]] for r in customers])
        assert ((probabilities >= 0) & (probabilities <= 1)).all()
        computed = classification_metrics(
            [r["actual_repeat"] for r in customers], probabilities
        )
        assert computed["brier"] == pytest.approx(score["test"]["brier"], abs=1e-6)
        assert computed["roc_auc"] == pytest.approx(score["test"]["roc_auc"], abs=1e-5)
