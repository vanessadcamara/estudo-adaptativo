from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_retention_run_stage_migration_preserves_history(tmp_path, monkeypatch):
    url = f'sqlite:///{tmp_path / "migration.db"}'
    monkeypatch.setenv('DATABASE_URL', url)
    config = Config('alembic.ini')
    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            conn.execute(text('CREATE TABLE study_sessions (id INTEGER PRIMARY KEY)'))
            conn.execute(text('CREATE TABLE retention_model_runs ('
                              'id INTEGER PRIMARY KEY, scope VARCHAR(80) NOT NULL, '
                              'session_id INTEGER REFERENCES study_sessions(id) ON DELETE RESTRICT, '
                              'created_at DATETIME NOT NULL, stage VARCHAR(20) NOT NULL, '
                              'active BOOLEAN NOT NULL, factor FLOAT NOT NULL, metrics JSON)'))
            conn.execute(text("INSERT INTO retention_model_runs "
                              "(scope, created_at, stage, active, factor) "
                              "VALUES ('question:1', CURRENT_TIMESTAMP, 'ativo', 1, 1.0)"))
        command.stamp(config, '0011_v16_full_fsrs_optimizer')
        command.upgrade(config, 'head')
        columns = inspect(engine).get_columns('retention_model_runs')
        assert next(c for c in columns if c['name'] == 'stage')['type'].length == 64
        with engine.begin() as conn:
            assert conn.scalar(text('SELECT stage FROM retention_model_runs')) == 'ativo'
            conn.execute(text("UPDATE retention_model_runs SET stage = 'otimizador_sem_melhoria'"))
            assert conn.scalar(text('SELECT stage FROM retention_model_runs')) == 'otimizador_sem_melhoria'
            conn.execute(text("UPDATE retention_model_runs SET stage = 'ativo'"))
        command.downgrade(config, '0011_v16_full_fsrs_optimizer')
        columns = inspect(engine).get_columns('retention_model_runs')
        assert next(c for c in columns if c['name'] == 'stage')['type'].length == 20
        with engine.connect() as conn:
            assert conn.scalar(text('SELECT stage FROM retention_model_runs')) == 'ativo'
    finally:
        engine.dispose()
