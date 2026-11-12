"""Seeds the T_Control_Autoreport_* tables in pycore's in-memory test database."""

import datetime as dt

import pandas as pd
import pytest

from pptcreator.kpi.registry import as_mapping_rows
from pptcreator.models.models import (
    AutoreportMappings,
    AutoreportRecipients,
    AutoreportTemplates,
)

TEMPLATE_ID = 1
BUCKET = "autoreport-test-bucket"


def template_rows(template_link: str, target_location: str | None = None) -> list[dict]:
    return [
        {
            "id": TEMPLATE_ID,
            "name": "VW KPI Weekly",
            "template_link": template_link,
            "language": "DE",
            "target_file_name": "VW_KPI_Report_{brand}_{current}_vs_{reference}",
            "target_location": target_location,
            "default_reference_weeks_back": 8,
            "commodity_charts_per_slide": None,
            "email_subject": "VW KPI Report {brand}: {current} vs. {reference}",
            "is_active": True,
        }
    ]


def recipient_rows() -> list[dict]:
    now = dt.datetime(2026, 11, 11, 12, 0, 0)
    return [
        {"id": 1, "template_id": TEMPLATE_ID, "email": "a@x.de", "brand": "Audi", "reference_timestamp": "KW37", "send_now": False, "is_active": True, "last_edited_at": now},
        {"id": 2, "template_id": TEMPLATE_ID, "email": "b@x.de", "brand": "Audi", "reference_timestamp": "KW37", "send_now": True, "is_active": True, "last_edited_at": now},
        {"id": 3, "template_id": TEMPLATE_ID, "email": "c@x.de", "brand": "Seat", "reference_timestamp": None, "send_now": False, "is_active": True, "last_edited_at": now},
        {"id": 4, "template_id": TEMPLATE_ID, "email": "d@x.de", "brand": "Seat", "reference_timestamp": "KW30", "send_now": True, "is_active": False, "last_edited_at": now},
        {"id": 5, "template_id": TEMPLATE_ID, "email": "", "brand": "Skoda", "reference_timestamp": "KW30", "send_now": False, "is_active": True, "last_edited_at": now},
        {"id": 6, "template_id": TEMPLATE_ID, "email": "A@x.de", "brand": "Audi", "reference_timestamp": "kw37", "send_now": False, "is_active": True, "last_edited_at": now},
    ]


@pytest.fixture
def seed_control_tables(data_repo):
    """Create the tables and insert template + mappings; recipients are optional."""

    def _seed(template_link: str, *, target_location: str | None = None, recipients: bool = True, source: str = "stub"):
        data_repo.database.create_all_tables()
        data_repo.write_table(model=AutoreportTemplates, df=pd.DataFrame(template_rows(template_link, target_location)))
        data_repo.write_table(model=AutoreportMappings, df=pd.DataFrame(as_mapping_rows(TEMPLATE_ID, source=source)))
        if recipients:
            data_repo.write_table(model=AutoreportRecipients, df=pd.DataFrame(recipient_rows()))
        return TEMPLATE_ID

    return _seed
