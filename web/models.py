from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from web.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    linkedin_creds_encrypted: Mapped[str | None] = mapped_column(Text)
    linkedin_session_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    schedule_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    schedule_time: Mapped[str] = mapped_column(String, default="08:00")
    google_drive_connected: Mapped[bool] = mapped_column(Boolean, default=False)
    google_drive_folder_id: Mapped[str | None] = mapped_column(String)

    runs: Mapped[list["Run"]] = relationship("Run", back_populates="user")
    jobs: Mapped[list["Job"]] = relationship("Job", back_populates="user")


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending|running|complete|failed|cancelled
    jobs_found: Mapped[int] = mapped_column(Integer, default=0)
    jobs_tailored: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    log_tail: Mapped[str | None] = mapped_column(Text)
    progress_pct: Mapped[int] = mapped_column(Integer, default=0)
    status_message: Mapped[str | None] = mapped_column(String)
    queue_position: Mapped[int] = mapped_column(Integer, default=0)

    user: Mapped["User"] = relationship("User", back_populates="runs")
    jobs: Mapped[list["Job"]] = relationship("Job", back_populates="run")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("runs.id"), nullable=False)
    company: Mapped[str | None] = mapped_column(String)
    title: Mapped[str | None] = mapped_column(String)
    url: Mapped[str | None] = mapped_column(String)
    location: Mapped[str | None] = mapped_column(String)
    posted_date: Mapped[str | None] = mapped_column(String)
    source: Mapped[str | None] = mapped_column(String)
    match_score: Mapped[int | None] = mapped_column(Integer)
    match_summary: Mapped[str | None] = mapped_column(Text)
    resume_path: Mapped[str | None] = mapped_column(Text)
    cover_letter_path: Mapped[str | None] = mapped_column(Text)
    resume_drive_url: Mapped[str | None] = mapped_column(Text)
    cover_letter_drive_url: Mapped[str | None] = mapped_column(Text)
    applied_status: Mapped[str] = mapped_column(String, default="pending")  # pending|applied|skipped
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="jobs")
    run: Mapped["Run"] = relationship("Run", back_populates="jobs")
