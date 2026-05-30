"""
Cup/Tournament model classes.

Cups are persisted in the DB (see data6.CupData).  These classes are
lightweight holders used when working with cup data in memory (admin
interface, protocol handlers).
"""


class Cup:
    def __init__(self, id, name, cup_type, status, created_on, finished_on=None):
        self.id = id
        self.name = name
        self.cup_type = cup_type   # 'competition' or 'winnerscup'
        self.status = status       # 'open', 'active', 'finished'
        self.created_on = created_on
        self.finished_on = finished_on

    @classmethod
    def from_row(cls, row):
        return cls(*row)


class CupParticipant:
    def __init__(self, profile_id, name, points, status):
        self.profile_id = profile_id
        self.name = name
        self.points = points
        self.status = status  # 'active', 'eliminated', 'winner', 'runner_up'

    @classmethod
    def from_row(cls, row):
        return cls(*row)


class CupMatch:
    def __init__(self, id, cup_id, match_id, round,
                 home_profile_id, away_profile_id,
                 winner_profile_id, status, played_on):
        self.id = id
        self.cup_id = cup_id
        self.match_id = match_id         # FK to matches table; None if not yet played
        self.round = round               # 1=final, 2=semis, 4=quarters, etc.
        self.home_profile_id = home_profile_id
        self.away_profile_id = away_profile_id
        self.winner_profile_id = winner_profile_id
        self.status = status             # 'pending', 'completed', 'walkover'
        self.played_on = played_on

    @classmethod
    def from_row(cls, row):
        return cls(*row)
