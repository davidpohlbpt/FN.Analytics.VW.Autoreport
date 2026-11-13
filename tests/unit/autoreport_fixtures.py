"""Seeds the T_Control_Autoreport_* tables in pycore's in-memory test database."""

import datetime as dt

import pandas as pd
import pytest

from pptcreator.kpi.registry import as_mapping_rows
from pptcreator.models.models import (
    AutoreportBrands,
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
            "commodity_charts_per_slide": None,
            "email_subject": "VW KPI Report {brand}: {current} vs. {reference}",
            "is_active": True,
        }
    ]


AUDI, SEAT, SKODA, PORSCHE = 1, 2, 3, 4


def brand_rows() -> list[dict]:
    return [
        {"id": AUDI, "brand_name": "Audi AG", "filter_value": "Audi", "is_active": True},
        {"id": SEAT, "brand_name": "SEAT", "filter_value": "Seat", "is_active": True},
        {"id": SKODA, "brand_name": "Skoda", "filter_value": "Skoda", "is_active": True},
        {"id": PORSCHE, "brand_name": "Porsche", "filter_value": "Porsche", "is_active": False},
    ]


def recipient_rows() -> list[dict]:
    now = dt.datetime(2026, 11, 11, 12, 0, 0)

    def row(id_, email, brand_id, primary, reference, send_now=False):
        return {
            "id": id_, "template_id": TEMPLATE_ID, "email": email, "brand_id": brand_id,
            "primary_date": primary, "reference_date": reference, "send_now": send_now,
            "last_edited_at": now,
        }

    # primary/reference are AnalyseZeitpunkt-style dates, as the frontend stores them
    return [
        row(1, "a@x.de", AUDI, "2025-11-28", "2025-11-18"),
        row(2, "b@x.de", AUDI, "2025-11-28", "2025-11-18", send_now=True),
        row(3, "c@x.de", SEAT, "2025-11-11", "2025-09-24"),
        row(4, "d@x.de", SEAT, "2025-10-28", "2025-08-29", send_now=True),
        row(5, "", SKODA, "2025-10-28", "2025-08-29"),          # missing email
        row(6, "A@x.de", AUDI, "2025-11-18", "2025-11-11"),     # same brand, other dates
        row(7, "e@x.de", PORSCHE, "2025-11-28", "2025-11-18"),  # inactive brand
    ]


@pytest.fixture
def seed_control_tables(data_repo):
    """Create the tables and insert template + mappings; recipients are optional."""

    def _seed(template_link: str, *, target_location: str | None = None, recipients: bool = True, source: str = "stub"):
        data_repo.database.create_all_tables()
        data_repo.write_table(model=AutoreportTemplates, df=pd.DataFrame(template_rows(template_link, target_location)))
        data_repo.write_table(model=AutoreportMappings, df=pd.DataFrame(as_mapping_rows(TEMPLATE_ID, source=source)))
        data_repo.write_table(model=AutoreportBrands, df=pd.DataFrame(brand_rows()))
        if recipients:
            data_repo.write_table(model=AutoreportRecipients, df=pd.DataFrame(recipient_rows()))
        return TEMPLATE_ID

    return _seed
