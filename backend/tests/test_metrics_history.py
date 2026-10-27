from datetime import datetime, timedelta

from app.db.models import MetricSample
from app.services import metrics_history


def _sample(moment: datetime, rx: float = 100.0, tx: float = 50.0) -> MetricSample:
    return MetricSample(
        timestamp=moment,
        cpu=10.0,
        ram=20.0,
        disk=30.0,
        load1=0.5,
        net_rx_rate=rx,
        net_tx_rate=tx,
        temp=40.0,
    )


def test_summarize_rows_skips_long_sampling_gap():
    start = datetime(2026, 10, 23, 0, 0, 0)
    rows = [
        _sample(start),
        _sample(start + timedelta(seconds=60)),
        _sample(start + timedelta(seconds=120)),
        _sample(start + timedelta(seconds=3720)),
        _sample(start + timedelta(seconds=3780)),
    ]

    summary = metrics_history.summarize_rows(rows, hours=24)

    assert summary["sample_count"] == 5
    assert summary["rx_total_bytes"] == 18000
    assert summary["tx_total_bytes"] == 9000


def test_summarize_rows_still_counts_normal_interval():
    start = datetime(2026, 10, 23, 0, 0, 0)
    rows = [
        _sample(start, rx=1000.0, tx=500.0),
        _sample(start + timedelta(seconds=60), rx=1000.0, tx=500.0),
    ]

    summary = metrics_history.summarize_rows(rows, hours=24)

    assert summary["rx_total_bytes"] == 60000
    assert summary["tx_total_bytes"] == 30000


def test_summarize_rows_ignores_non_positive_interval():
    start = datetime(2026, 10, 23, 0, 0, 0)
    rows = [
        _sample(start),
        _sample(start),
        _sample(start + timedelta(seconds=60)),
    ]

    summary = metrics_history.summarize_rows(rows, hours=24)

    assert summary["rx_total_bytes"] == 6000
    assert summary["tx_total_bytes"] == 3000
