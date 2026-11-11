import sqlalchemy as sa
from pycore.easy import DeclarativeBase
from sqlalchemy.orm import Mapped, mapped_column

from pptcreator.config import settings
from pptcreator.models.enum import Languages

SCHEMA = settings.app_db_schema


class Mappings(DeclarativeBase):
    __tablename__ = "T_CONTROL_PptCreator_Mappings"
    __table_args__ = {"schema": SCHEMA, "extend_existing": True}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    """Internal identifier for mapping
    """

    template_object_name: Mapped[str] = mapped_column(sa.String(500))
    """Object identifier for object in the ppt templates
    """

    menu_item_id: Mapped[int]
    """Menu item id in DQN
    """

    report_id: Mapped[int]
    """Report Id in DQN
    """

    tile_id: Mapped[int]
    """Tile identifier in DQN
    """

    chart_id: Mapped[int]
    """Chart identifier in DQN
    """

    template_id: Mapped[int] = mapped_column(
        sa.ForeignKey(f"{SCHEMA}.T_CONTROL_PptCreator_Templates.id"),
    )
    """Template identifier
    """


class Templates(DeclarativeBase):
    __tablename__ = "T_CONTROL_PptCreator_Templates"
    __table_args__ = {"schema": SCHEMA, "extend_existing": True}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    """Internal identifier for template
    """

    template_link: Mapped[str] = mapped_column(sa.String(500))
    """Link to the ppt template in Azure Blob Storage
    """

    language: Mapped[Languages] = mapped_column(
        sa.Enum(Languages, values_callable=lambda e: [m.value for m in e])
    )

    filter_column: Mapped[str | None] = mapped_column(sa.String(500))  # nullable=True!
    """Filter column for the project, if None then no filtering is applied
    """

    is_active: Mapped[bool]
    """Indicates whether the template is active
    """

    target_file_name: Mapped[str] = mapped_column(sa.String(500))
    """Target file name for the generated ppt
    """

    target_blob_container: Mapped[str] = mapped_column(sa.String(500))
    """Target blob container for the generated ppt
    """

    headline_substring: Mapped[str] = mapped_column(sa.String(500))
    """Substring displayed in the headline plus slide specific filter string
    """


class Recipients(DeclarativeBase):
    __tablename__ = "T_CONTROL_PptCreator_Recipients"
    __table_args__ = {"schema": SCHEMA, "extend_existing": True}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    """Internal identifier for recipient
    """

    recipient_email: Mapped[str] = mapped_column(sa.String(500))
    """Email of the recipient
    """

    template_id: Mapped[int] = mapped_column(
        sa.ForeignKey(f"{SCHEMA}.T_CONTROL_PptCreator_Templates.id"),
    )
    """Template identifier
    """

    is_active: Mapped[bool]
    """Indicates whether the recipient is active
    """
