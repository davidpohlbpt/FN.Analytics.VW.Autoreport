from types import SimpleNamespace

import pytest
import sqlalchemy as sa

from pptcreator.models.models import AutoreportRuns
from pptcreator.utils import run_log


@pytest.fixture
def runs_engine(monkeypatch):
    engine = sa.create_engine("sqlite://").execution_options(
        schema_translate_map={"control": None}
    )
    table = AutoreportRuns.__table__
    table.create(engine)
    with engine.begin() as connection:
        connection.execute(
            table.insert(),
            [
                {
                    "run_id": "run-1",
                    "template_id": 1,
                    "recipients": "a@example.com",
                    "recipient_id": recipient_id,
                    "brand": "Audi",
                    "current_period": "KW45",
                    "reference_period": reference_period,
                    "status": "processing",
                }
                for recipient_id, reference_period in [(42, "KW37"), (43, "KW38")]
            ],
        )
    monkeypatch.setattr(run_log, "database", SimpleNamespace(engine=engine))
    yield engine
    engine.dispose()


@pytest.mark.parametrize("recipient_id", [42, None])
def test_status_update_uses_the_simplified_runs_schema(runs_engine, recipient_id):
    run_log.update_status(
        "run-1", "Audi", "KW37", status="rendered", recipient_id=recipient_id
    )

    with runs_engine.connect() as connection:
        rows = connection.execute(
            sa.select(AutoreportRuns.__table__).order_by(AutoreportRuns.id)
        ).mappings().all()
    assert [row["status"] for row in rows] == ["rendered", "processing"]
    assert rows[0]["updated_at"] is not None
    assert rows[0]["recipients"] == "a@example.com"
    assert rows[0]["current_period"] == "KW45"
    assert rows[0]["reference_period"] == "KW37"


def test_render_updates_run_without_persisting_the_s3_key(runs_engine):
    from pptcreator.creator.get_config.get_kpi_deck_config import ReportRequest
    from pptcreator.lambdas.render import update_run_log

    request = ReportRequest.from_event(
        {
            "template_id": 1,
            "brand": "Audi",
            "current_period": "KW45",
            "reference_period": "KW37",
            "recipients": ["a@example.com"],
            "recipient_ids": [42],
            "run_id": "run-1",
        }
    )
    update_run_log(
        request, SimpleNamespace(status="rendered", s3_key="reports/deck.pptx", error=None)
    )

    with runs_engine.connect() as connection:
        status = connection.execute(
            sa.select(AutoreportRuns.status).where(AutoreportRuns.recipient_id == 42)
        ).scalar_one()
    assert status == "rendered"
