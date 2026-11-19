"""Runs against the actual official Py-FSRS when installed by pip install ."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from app import statistical_retention as stat


@pytest.mark.parametrize('kind', ['topic', 'question'])
def test_official_fsrs6_replay_and_prediction(kind):
    pytest.importorskip('fsrs')
    base=datetime(2026, 1, 1, tzinfo=timezone.utc)
    if kind == 'topic':
        records=[SimpleNamespace(
            id=i+1, topic_id=7, created_at=base + timedelta(days=i*8),
            grade=4, recall_level=3, accuracy_level=3, assistance_level=0,
            difficulty=1, critical_gap=False) for i in range(3)]
    else:
        records=[SimpleNamespace(
            id=i+1, question_id=7, created_at=base + timedelta(days=i*8),
            is_correct=True, confidence=3) for i in range(3)]
    observations,scheduler,card=stat._replay(records,kind)
    assert len(observations) == 2
    assert all(0 <= x['predicted'] <= 1 for x in observations)
    assert card.stability is not None and card.stability > 0
    estimate=stat.item_estimate(records, kind, base + timedelta(days=24))
    assert estimate is not None
    assert 0 <= estimate['expected_recall_percent'] <= 100
    assert 1 <= estimate['fsrs_interval_days'] <= 60
