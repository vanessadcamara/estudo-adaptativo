"""v0.12: overdue protection and evidence-based spacing."""
from datetime import datetime, timedelta, timezone
from app.db import get_db
from app.engine import build_queue, observed_retention_interval
from app.models import StudySession, TopicReview


def test_retention_adjustment_requires_evidence_and_uses_actual_elapsed_time():
    now = datetime(2026, 11, 19, tzinfo=timezone.utc)
    def make(grades, spacing=15):
        return [TopicReview(grade=g, difficulty=1, critical_gap=False,
                            recall_level=3 if g == 4 else 0, accuracy_level=3 if g == 4 else 0,
                            assistance_level=0, gap_level=0 if g == 4 else 3,
                            created_at=now + timedelta(days=spacing*i))
                for i, g in enumerate(grades)]
    success = lambda r: r.grade >= 3
    assert observed_retention_interval(make([4, 4]), 30, success) == 30
    good = observed_retention_interval(make([4]*13, spacing=31), 30, success)
    poor = observed_retention_interval(make([4]+[0]*12, spacing=1), 30, success)
    assert good > 30
    assert poor < 30
    assert 23 <= poor < good <= 38


def test_long_overdue_topic_recovers_from_diversification_penalty(client):
    subject = client.post('/api/subjects', json={'name': 'Bancários'}).json()['id']
    hard = client.post('/api/topics', json={'subject_id': subject, 'title': 'Mercado aberto'}).json()['id']
    client.post('/api/topics', json={'subject_id': subject, 'title': 'Redesconto'})
    now = datetime.now(timezone.utc)
    with next(client.app.dependency_overrides[get_db]()) as db:
        for i in range(3):
            db.add(StudySession(id=900+i, opened_at=now-timedelta(days=35-7*i)))
            db.add(TopicReview(topic_id=hard, session_id=900+i, grade=0,
                               difficulty=3, critical_gap=True,
                               created_at=now-timedelta(days=35-7*i)))
        db.commit()
        row = next(x for x in build_queue(db, now=now, subject_id=subject)['topics'] if x['id'] == hard)
    assert row['recent_review_count_3_sessions'] == 3
    assert row['overdue_protection_strength'] == 1
    assert row['diversification_penalty'] == 0
    assert row['maintenance_required']
