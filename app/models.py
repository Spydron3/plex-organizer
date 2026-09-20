from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


class MediaType(str, Enum):
    movie = "movie"
    tv = "tv"
    music = "music"


class PlanStatus(str, Enum):
    pending = "pending"
    executed = "executed"
    cancelled = "cancelled"


class ItemStatus(str, Enum):
    pending = "pending"
    skip = "skip"
    done = "done"
    conflict = "conflict"
    error = "error"
    unmatched = "unmatched"


class LibraryPath(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    path: str
    type: MediaType
    enabled: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class LibraryPathCreate(SQLModel):
    path: str
    type: MediaType


class ScanPlan(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    library_id: int = Field(foreign_key="librarypath.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: PlanStatus = PlanStatus.pending
    skipped_up_to_date: int = 0


class PlanItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    plan_id: int = Field(foreign_key="scanplan.id")
    source_path: str
    target_path: str
    media_type: MediaType
    title: Optional[str] = None
    year: Optional[int] = None
    season: Optional[int] = None
    episode: Optional[int] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    track: Optional[int] = None
    matched: bool = False
    status: ItemStatus = ItemStatus.pending
    error_message: Optional[str] = None


class PlanItemUpdate(SQLModel):
    status: Optional[ItemStatus] = None
    target_path: Optional[str] = None


class AppSetting(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: str
