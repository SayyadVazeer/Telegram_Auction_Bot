"""Media file storage model — persists Telegram file_ids for GIF/media files."""

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class MediaFile(Base):
    __tablename__ = "media_files"

    id: Mapped[int] = mapped_column(primary_key=True)

    key: Mapped[str] = mapped_column(
        String(32),
        unique=True,
        nullable=False,
        index=True,
    )
    # e.g. "bid1", "bid2", "bid3", "once", "twice", "sold", "unsold"

    telegram_file_id: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
    )

    telegram_unique_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    local_path: Mapped[str | None] = mapped_column(
        String(256),
        nullable=True,
    )
    # e.g. "data/bid1.gif"

    media_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="animation",
    )
    # "animation" for GIF, "photo" for JPEG

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
