import asyncio
from typing import Optional

from app.tfmkt import TfmktClient

# upstream score.additionType -> result note, as the English website shows it
RESULT_NOTES = {"after_extra_time": "AET", "after_shootout": "on pens"}


async def get_club_fixtures(tfmkt: TfmktClient, club_id: str, season_id: Optional[str] = None) -> dict:
    """
    Played and upcoming matches of a club for a season (current season when `season_id` is omitted), by kickoff.

    `date` and `time` are the kickoff in UTC; `time` is null when upstream has not fixed the kickoff time yet.
    Score fields are null for matches that are not played yet.
    """
    games = (await tfmkt.club_fixtures(club_id, season_id)).get("games") or []
    games.sort(key=lambda game: game["baseDetails"]["date"].get("dateTimeUTC") or "")

    competitions, clubs = await asyncio.gather(
        tfmkt.competitions(game["baseDetails"]["competitionId"] for game in games),
        tfmkt.clubs(game[side]["clubId"] for game in games for side in ("homeClub", "awayClub")),
    )

    def team(side: dict) -> dict:
        """`{id, name, tablePosition}` for the home or away side of a match."""
        return {
            "id": str(side["clubId"]),
            "name": clubs.get(str(side["clubId"]), {}).get("name"),
            "tablePosition": side.get("rank"),
        }

    fixtures = []
    for game in games:
        details, score = game["baseDetails"], game.get("score") or {}
        kickoff = details["date"].get("dateTimeUTC") or ""
        home, away = team(game["homeClub"]), team(game["awayClub"])
        competition = competitions.get(str(details["competitionId"]), {})
        venue = "home" if home["id"] == str(club_id) else "away" if away["id"] == str(club_id) else None
        other = {"home": "away", "away": "home"}.get(venue)
        opponent = {"home": home, "away": away}.get(other)
        played = score.get("home") is not None and score.get("away") is not None
        addition = score.get("additionType")
        note = RESULT_NOTES.get(addition, score.get("addition")) if played and addition != "none" else None
        fixtures.append({
            "matchId": str(game["gameId"]),
            "competitionName": competition.get("name"),
            "competitionId": details["competitionId"],
            "competitionUrl": competition.get("relativeUrl"),
            "matchday": str(details["gameDay"]) if details.get("gameDay") else None,
            "date": kickoff[:10] or None,
            "time": (kickoff[11:16] or None) if details["date"].get("isTimeDefined") else None,
            "homeClub": home,
            "awayClub": away,
            "venue": venue,
            "opponent": {"id": opponent["id"], "name": opponent["name"]} if opponent else None,
            "resultRaw": f"{score['home']}:{score['away']}" + (f" {note}" if note else "") if played else None,
            "goalsFor": score[venue] if played and venue else None,
            "goalsAgainst": score[other] if played and other else None,
            "resultNote": note,
            "attendance": (game.get("extendedDetails") or {}).get("crowdSize") or None,  # 0 means unknown
        })

    season_ids = {str(game["baseDetails"]["seasonId"]) for game in games}
    return {
        "id": club_id,
        "seasonId": season_id or (season_ids.pop() if len(season_ids) == 1 else None),
        "fixtures": fixtures,
    }
