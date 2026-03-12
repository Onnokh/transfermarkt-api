import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.services.base import TransfermarktBase
from app.utils.utils import extract_from_url
from app.utils.xpath import Clubs


def _norm_space(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    return " ".join(text.split())


def _parse_ddmmyyyy_to_iso(text: Optional[str]) -> Optional[str]:
    """Parse Transfermarkt schedule dates like 'Fri 01/08/2025' into ISO '2025-08-01'."""
    text = _norm_space(text)
    if not text:
        return None

    m = re.search(r"(?P<day>\d{2})/(?P<month>\d{2})/(?P<year>\d{4})", text)
    if not m:
        m = re.search(r"(?P<day>\d{2})\.(?P<month>\d{2})\.(?P<year>\d{4})", text)
    if not m:
        return text

    year = m.group("year")
    month = m.group("month")
    day = m.group("day")
    return f"{year}-{month}-{day}"


def _parse_time_to_24h(text: Optional[str]) -> Optional[str]:
    text = _norm_space(text)
    if not text or text.lower() == "unknown":
        return None
    try:
        return datetime.strptime(text, "%I:%M %p").strftime("%H:%M")
    except ValueError:
        return text


def _parse_int_thousands(text: Optional[str]) -> Optional[int]:
    text = _norm_space(text)
    if not text or text == "-":
        return None
    digits = re.sub(r"[^0-9]", "", text)
    return int(digits) if digits else None


def _parse_team_name_and_pos(text: Optional[str]) -> tuple[Optional[str], Optional[int]]:
    """Parse strings like 'Hertha BSC (6.)' into ('Hertha BSC', 6)."""
    text = _norm_space(text)
    if not text:
        return None, None

    m = re.match(r"^(?P<name>.*?)(?:\s+\((?P<pos>\d+)\.\))?$", text)
    if not m:
        return text, None
    name = _norm_space(m.group("name"))
    pos = m.group("pos")
    return name, int(pos) if pos else None


def _extract_match_id(href: Optional[str]) -> Optional[str]:
    if not href:
        return None
    m = re.search(r"/spielbericht/(?P<id>\d+)", href)
    return m.group("id") if m else None


@dataclass
class TransfermarktClubFixtures(TransfermarktBase):
    """Retrieve a club's fixtures for a season from Transfermarkt's schedule page."""

    club_id: str = None
    season_id: Optional[str] = None
    URL: str = "https://www.transfermarkt.com/-/spielplan/verein/{club_id}{season_part}/plus/1"

    def __post_init__(self) -> None:
        season_part = f"/saison_id/{self.season_id}" if self.season_id else ""
        self.URL = self.URL.format(club_id=self.club_id, season_part=season_part)
        self.page = self.request_url_page()
        self.raise_exception_if_not_found(xpath=Clubs.Fixtures.CLUB_NAME)
        self.__update_season_id()

    def __update_season_id(self) -> None:
        if not self.season_id:
            self.season_id = self.get_text_by_xpath(Clubs.Fixtures.SEASON_SELECTED)

    def __iter_fixture_tables(self):
        required_headers = {"Date", "Home team", "Away team", "Result"}
        for h2 in self.page.xpath(Clubs.Fixtures.SECTIONS):
            table = h2.xpath("following::table[1]")
            if not table:
                continue
            table = table[0]
            headers = [_norm_space(t) for t in table.xpath(Clubs.Fixtures.TABLE_HEADERS) if _norm_space(t)]
            if not required_headers.issubset(set(headers)):
                continue
            yield h2, headers, table

    def __parse_fixture_rows(self, headers: list[str], table) -> list[dict]:
        has_matchday = "Matchday" in headers
        fixtures: list[dict] = []

        for row in table.xpath(Clubs.Fixtures.TABLE_ROWS):
            tds = row.xpath("./td")
            if not tds:
                continue

            # Expected td layout (detailed view):
            # - with Matchday: 11 tds
            # - without Matchday: 10 tds
            if has_matchday and len(tds) < 11:
                continue
            if (not has_matchday) and len(tds) < 10:
                continue

            offset = 1 if has_matchday else 0
            matchday_td = tds[0] if has_matchday else None
            date_td = tds[0 + offset]
            time_td = tds[1 + offset]
            home_logo_td = tds[2 + offset]
            home_name_td = tds[3 + offset]
            away_logo_td = tds[4 + offset]
            away_name_td = tds[5 + offset]
            system_td = tds[6 + offset]
            coach_td = tds[7 + offset]
            attendance_td = tds[8 + offset]
            result_td = tds[9 + offset]

            matchday = _norm_space("".join(matchday_td.xpath(".//text()"))) if matchday_td is not None else None
            date_raw = _norm_space("".join(date_td.xpath(".//text()")))
            time_raw = _norm_space("".join(time_td.xpath(".//text()")))

            home_url = home_logo_td.xpath(".//a[contains(@href,'/verein/')]/@href") or home_name_td.xpath(
                ".//a[contains(@href,'/verein/')]/@href",
            )
            away_url = away_logo_td.xpath(".//a[contains(@href,'/verein/')]/@href") or away_name_td.xpath(
                ".//a[contains(@href,'/verein/')]/@href",
            )
            home_id = extract_from_url(home_url[0]) if home_url else None
            away_id = extract_from_url(away_url[0]) if away_url else None

            home_name_raw = _norm_space("".join(home_name_td.xpath(".//text()")))
            away_name_raw = _norm_space("".join(away_name_td.xpath(".//text()")))
            home_name, home_pos = _parse_team_name_and_pos(home_name_raw)
            away_name, away_pos = _parse_team_name_and_pos(away_name_raw)

            result_raw = _norm_space("".join(result_td.xpath(".//text()")))
            system_of_play = _norm_space("".join(system_td.xpath(".//text()")))
            coach = _norm_space("".join(coach_td.xpath(".//text()")))
            attendance = _parse_int_thousands(_norm_space("".join(attendance_td.xpath(".//text()"))))
            match_href = (result_td.xpath(".//a[contains(@href,'/spielbericht/')]/@href") or [None])[0]
            match_id = _extract_match_id(match_href)

            # Parse goals from result
            goals_home = goals_away = None
            result_note = None
            m = re.search(r"(?P<h>\d+):(?P<a>\d+)", result_raw or "")
            if m:
                goals_home = int(m.group("h"))
                goals_away = int(m.group("a"))
                note = _norm_space(re.sub(r"\d+:\d+", "", result_raw or ""))
                result_note = note or None

            venue = None
            opponent = None
            goals_for = goals_against = None
            if home_id == self.club_id:
                venue = "home"
                opponent = {"id": away_id, "name": away_name}
                if goals_home is not None and goals_away is not None:
                    goals_for, goals_against = goals_home, goals_away
            elif away_id == self.club_id:
                venue = "away"
                opponent = {"id": home_id, "name": home_name}
                if goals_home is not None and goals_away is not None:
                    goals_for, goals_against = goals_away, goals_home

            fixtures.append(
                {
                    "matchId": match_id,
                    "matchday": matchday,
                    "date": _parse_ddmmyyyy_to_iso(date_raw),
                    "time": _parse_time_to_24h(time_raw),
                    "homeClub": {"id": home_id, "name": home_name, "tablePosition": home_pos},
                    "awayClub": {"id": away_id, "name": away_name, "tablePosition": away_pos},
                    "venue": venue,
                    "opponent": opponent,
                    "resultRaw": result_raw,
                    "goalsFor": goals_for,
                    "goalsAgainst": goals_against,
                    "resultNote": result_note,
                    "attendance": attendance,
                    "systemOfPlay": system_of_play,
                    "coach": coach,
                },
            )

        return fixtures

    def get_club_fixtures(self) -> dict:
        self.response["id"] = self.club_id
        self.response["seasonId"] = self.season_id
        fixtures: list[dict] = []

        for h2, headers, table in self.__iter_fixture_tables():
            comp_name = _norm_space("".join(h2.xpath(".//text()")))
            comp_href = (
                h2.xpath(".//a[contains(@href,'/wettbewerb/') or contains(@href,'/pokalwettbewerb/')]/@href") or [None]
            )[0]
            comp_id = extract_from_url(comp_href) if comp_href else None

            for f in self.__parse_fixture_rows(headers=headers, table=table):
                f["competitionName"] = comp_name
                f["competitionId"] = comp_id
                f["competitionUrl"] = comp_href
                fixtures.append(f)

        self.response["fixtures"] = fixtures
        return self.response
