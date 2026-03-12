import datetime
from typing import Optional

from app.schemas.base import AuditMixin, TransfermarktBaseModel


class ClubFixtureTeam(TransfermarktBaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    table_position: Optional[int] = None


class ClubFixtureOpponent(TransfermarktBaseModel):
    id: Optional[str] = None
    name: Optional[str] = None


class ClubFixture(TransfermarktBaseModel):
    match_id: Optional[str] = None
    competition_name: Optional[str] = None
    competition_id: Optional[str] = None
    competition_url: Optional[str] = None
    matchday: Optional[str] = None
    date: Optional[datetime.date] = None
    time: Optional[str] = None
    home_club: ClubFixtureTeam
    away_club: ClubFixtureTeam
    venue: Optional[str] = None
    opponent: Optional[ClubFixtureOpponent] = None
    result_raw: Optional[str] = None
    goals_for: Optional[int] = None
    goals_against: Optional[int] = None
    result_note: Optional[str] = None
    attendance: Optional[int] = None
    system_of_play: Optional[str] = None
    coach: Optional[str] = None


class ClubFixtures(TransfermarktBaseModel, AuditMixin):
    id: str
    season_id: Optional[str] = None
    fixtures: list[ClubFixture]
