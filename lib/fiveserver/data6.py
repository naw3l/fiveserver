"""
Data-layer for PES6
"""

from twisted.internet import defer
from datetime import timedelta
from fiveserver.model import user
from fiveserver import data


class UserData(data.UserData):
    """
    Same as PES5 UserData
    """

class ProfileData(data.ProfileData):
    """
    Not quite the same as PES ProfileData, because
    of new fields: rating, comment
    """

    def __init__(self, dbController):
        self.dbController = dbController

    MEDAL_COLS = ('competition_gold,competition_silver,'
                  'winnerscup_gold,winnerscup_silver')

    def _rowToProfile(self, row):
        (id, userId, ordinal, name, rank, rating,
         points, disconnects, updatedOn, secondsPlayed, comment,
         competition_gold, competition_silver,
         winnerscup_gold, winnerscup_silver) = row
        p = user.Profile(ordinal)
        p.id = id
        p.userId = userId
        p.name = name
        p.rank = rank
        p.rating = rating
        p.points = points
        p.disconnects = disconnects
        p.updatedOn = updatedOn
        p.playTime = timedelta(seconds=secondsPlayed)
        p.comment = comment
        p.competition_gold = competition_gold or 0
        p.competition_silver = competition_silver or 0
        p.winnerscup_gold = winnerscup_gold or 0
        p.winnerscup_silver = winnerscup_silver or 0
        return p

    @defer.inlineCallbacks
    def get(self, id):
        sql = ('SELECT id,user_id,ordinal,name,`rank`,'
               'rating,points,disconnects,updated_on,seconds_played,comment,'
               + self.MEDAL_COLS +
               ' FROM profiles WHERE deleted = 0 AND id = %s')
        rows = yield self.dbController.dbRead(0, sql, id)
        defer.returnValue([self._rowToProfile(row) for row in rows])

    @defer.inlineCallbacks
    def getByUserId(self, userId):
        sql = ('SELECT id,user_id,ordinal,name,`rank`,'
               'rating,points,disconnects,updated_on,seconds_played,comment,'
               + self.MEDAL_COLS +
               ' FROM profiles WHERE deleted = 0 AND user_id = %s '
               'ORDER BY updated_on ASC')
        rows = yield self.dbController.dbRead(0, sql, userId)
        defer.returnValue([self._rowToProfile(row) for row in rows])

    @defer.inlineCallbacks
    def browse(self, offset=0, limit=30):
        sql = 'SELECT count(id) FROM profiles WHERE deleted = 0'
        rows = yield self.dbController.dbRead(0, sql)
        total = int(rows[0][0])
        sql = ('SELECT id,user_id,ordinal,name,`rank`,'
               'rating,points,disconnects,updated_on,seconds_played,comment,'
               + self.MEDAL_COLS +
               ' FROM profiles WHERE deleted = 0 '
               'ORDER BY name LIMIT %s OFFSET %s')
        rows = yield self.dbController.dbRead(0, sql, limit, offset)
        defer.returnValue((total, [self._rowToProfile(row) for row in rows]))

    @defer.inlineCallbacks
    def store(self, p):
        sql = ('INSERT INTO profiles '
               '(id,user_id,ordinal,name,`rank`,rating,points,disconnects,'
               'seconds_played,comment,'
               'competition_gold,competition_silver,'
               'winnerscup_gold,winnerscup_silver) '
               'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) '
               'ON DUPLICATE KEY UPDATE '
               'deleted=0, user_id=%s, ordinal=%s, name=%s, '
               '`rank`=%s, rating=%s, points=%s, '
               'disconnects=%s, seconds_played=%s, comment=%s, '
               'competition_gold=%s, competition_silver=%s, '
               'winnerscup_gold=%s, winnerscup_silver=%s')
        params = (
            p.id, p.userId, p.index, p.name,
            p.rank, p.rating, p.points, p.disconnects,
            int(p.playTime.total_seconds()), p.comment,
            p.competition_gold, p.competition_silver,
            p.winnerscup_gold, p.winnerscup_silver,
            # ON DUPLICATE KEY UPDATE values
            p.userId, p.index, p.name, p.rank,
            p.rating, p.points, p.disconnects,
            int(p.playTime.total_seconds()), p.comment,
            p.competition_gold, p.competition_silver,
            p.winnerscup_gold, p.winnerscup_silver,
        )
        yield self.dbController.dbWrite(0, sql, *params)
        defer.returnValue(True)

    @defer.inlineCallbacks
    def findByName(self, profileName):
        sql = ('SELECT id,user_id,ordinal,name,`rank`,'
               'rating,points,disconnects,updated_on,seconds_played,comment,'
               + self.MEDAL_COLS +
               ' FROM profiles WHERE deleted = 0 AND name = %s')
        rows = yield self.dbController.dbRead(0, sql, profileName)
        defer.returnValue([self._rowToProfile(row) for row in rows])

    @defer.inlineCallbacks
    def findByNameLike(self, prefix, limit=20):
        sql = ('SELECT id,user_id,ordinal,name,`rank`,'
               'rating,points,disconnects,updated_on,seconds_played,comment,'
               + self.MEDAL_COLS +
               ' FROM profiles WHERE deleted = 0 AND name LIKE %s '
               'ORDER BY name LIMIT %s')
        safe = prefix.replace('%', r'\%').replace('_', r'\_') + '%'
        rows = yield self.dbController.dbRead(0, sql, safe, limit)
        defer.returnValue([self._rowToProfile(row) for row in rows])


class MatchData:

    def __init__(self, dbController):
        self.dbController = dbController

    @defer.inlineCallbacks
    def getGames(self, profileId):
        sql = ('SELECT count(id) FROM matches_played '
               'WHERE profile_id=%s')
        rows = yield self.dbController.dbRead(0, sql, profileId)
        defer.returnValue(rows[0][0])

    @defer.inlineCallbacks
    def getWins(self, profileId):
        sql = ('SELECT count(matches.id) FROM matches, matches_played '
               'WHERE matches.id=matches_played.match_id AND profile_id=%s '
               'AND ((home=1 and score_home>score_away) OR '
               '(home=0 and score_home<score_away))')
        rows = yield self.dbController.dbRead(0, sql, profileId)
        defer.returnValue(rows[0][0])

    @defer.inlineCallbacks
    def getLosses(self, profileId):
        sql = ('SELECT count(matches.id) FROM matches, matches_played '
               'WHERE matches.id=matches_played.match_id AND profile_id=%s '
               'AND ((home=1 and score_home<score_away) OR '
               '(home=0 and score_home>score_away))')
        rows = yield self.dbController.dbRead(0, sql, profileId)
        defer.returnValue(rows[0][0])

    @defer.inlineCallbacks
    def getDraws(self, profileId):
        sql = ('SELECT count(matches.id) FROM matches, matches_played '
               'WHERE matches.id=matches_played.match_id AND profile_id=%s '
               'AND score_home=score_away')
        rows = yield self.dbController.dbRead(0, sql, profileId)
        defer.returnValue(rows[0][0])

    @defer.inlineCallbacks
    def getGoalsHome(self, profileId):
        sql = ('SELECT sum(score_home),sum(score_away) '
               'FROM matches, matches_played '
               'WHERE matches.id=matches_played.match_id '
               'AND profile_id=%s AND home=1')
        rows = yield self.dbController.dbRead(0, sql, profileId)
        scored = rows[0][0] or 0
        allowed = rows[0][1] or 0
        defer.returnValue((int(scored), int(allowed)))

    @defer.inlineCallbacks
    def getGoalsAway(self, profileId):
        sql = ('SELECT sum(score_away),sum(score_home) '
               'FROM matches, matches_played '
               'WHERE matches.id=matches_played.match_id '
               'AND profile_id=%s AND home=0')
        rows = yield self.dbController.dbRead(0, sql, profileId)
        scored = rows[0][0] or 0
        allowed = rows[0][1] or 0
        defer.returnValue((int(scored), int(allowed)))

    @defer.inlineCallbacks
    def getStreaks(self, profileId):
        sql = ('SELECT wins, best FROM streaks '
               'WHERE profile_id=%s')
        rows = yield self.dbController.dbRead(0, sql, profileId)
        wins, best = 0, 0
        if len(rows)>0:
            wins, best = rows[0][0], rows[0][1]
        defer.returnValue((wins, best))

    @defer.inlineCallbacks
    def getLastTeamsUsed(self, profileId, numMatches):
        sql = ('SELECT match_id, team_id_home, team_id_away, home '
               'FROM matches_played, matches '
               'WHERE profile_id=%s AND matches.id=match_id '
               'ORDER BY match_id DESC LIMIT %s')
        args = (profileId, numMatches,)
        rows = yield self.dbController.dbRead(0, sql, *args)
        teams = []
        for row in rows:
            match_id, team_id_home, team_id_away, home = row
            if home:
                teams.append(team_id_home)
            else:
                teams.append(team_id_away)
        defer.returnValue(teams)

    @defer.inlineCallbacks
    def store(self, match):
        matchId = yield self.dbController.dbWriteInteraction(
            0, self._storeTxn, match)
        defer.returnValue(matchId)

    def _storeTxn(self, transaction, match):
        def _writeStreak(profile_id, win):
            wins, best = 0, 0
            sql = ('SELECT wins, best FROM streaks '
                   'WHERE profile_id=%s')
            transaction.execute(sql, (profile_id,))
            data = transaction.fetchall()
            if len(data)>0:
                wins, best = data[0][0], data[0][1]
            if win:
                wins += 1
                best = max(wins, best)
            else:
                wins = 0
            sql = ('INSERT INTO streaks (profile_id, wins, best) '
                   'VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE '
                   'wins=%s, best=%s')
            transaction.execute(sql, (
                profile_id, wins, best, wins, best))

        # record match result
        sql = ('INSERT INTO matches '
               '(score_home, score_away, team_id_home, team_id_away) '
               'VALUES (%s,%s,%s,%s)')
        transaction.execute(sql, ( 
            match.score_home, match.score_away, 
            match.teamSelection.home_team_id, match.teamSelection.away_team_id))
        transaction.execute('SELECT LAST_INSERT_ID()')
        matchId = transaction.fetchall()[0][0]
        # record players of the match
        home_players = [match.teamSelection.home_captain]
        home_players.extend(match.teamSelection.home_more_players)
        away_players = [match.teamSelection.away_captain]
        away_players.extend(match.teamSelection.away_more_players)
        for profile in home_players:
            sql = ('INSERT INTO matches_played (match_id, profile_id, home) '
                   'VALUES (%s, %s, 1)')
            transaction.execute(sql, (matchId, profile.id))
        for profile in away_players:
            sql = ('INSERT INTO matches_played (match_id, profile_id, home) '
                   'VALUES (%s, %s, 0)')
            transaction.execute(sql, (matchId, profile.id))
        # update winning streaks
        if match.score_home > match.score_away:
            # home win
            for profile in home_players:
                _writeStreak(profile.id, True)
            for profile in away_players:
                _writeStreak(profile.id, False)
        elif match.score_home < match.score_away:
            # away win
            for profile in home_players:
                _writeStreak(profile.id, False)
            for profile in away_players:
                _writeStreak(profile.id, True)
        else:
            # draw
            for profile in home_players:
                _writeStreak(profile.id, False)
            for profile in away_players:
                _writeStreak(profile.id, False)
        return matchId


class CupData:
    """
    Data layer for the cup/tournament system.

    Supports knockout brackets. When a cup is activated the first round
    of matches is generated from the enrolled participants (sorted by points,
    top seed vs bottom seed). As match results are recorded the next round is
    generated automatically until a winner is determined.
    """

    def __init__(self, dbController):
        self.dbController = dbController

    # ------------------------------------------------------------------
    # Cup lifecycle
    # ------------------------------------------------------------------

    @defer.inlineCallbacks
    def createCup(self, name, cup_type='winnerscup'):
        """Create a new cup in 'open' state. Returns cup id."""
        cup_id = yield self.dbController.dbWriteInteraction(
            0, self._createCupTxn, name, cup_type)
        defer.returnValue(cup_id)

    def _createCupTxn(self, txn, name, cup_type):
        txn.execute(
            "INSERT INTO cups (name, cup_type, status) VALUES (%s, %s, 'open')",
            (name, cup_type))
        txn.execute('SELECT LAST_INSERT_ID()')
        return txn.fetchall()[0][0]

    @defer.inlineCallbacks
    def getCupById(self, cup_id):
        sql = 'SELECT id,name,cup_type,status,created_on,finished_on FROM cups WHERE id=%s'
        rows = yield self.dbController.dbRead(0, sql, cup_id)
        defer.returnValue(rows[0] if rows else None)

    @defer.inlineCallbacks
    def listCups(self, status=None):
        if status:
            sql = ('SELECT id,name,cup_type,status,created_on,finished_on '
                   'FROM cups WHERE status=%s ORDER BY created_on DESC')
            rows = yield self.dbController.dbRead(0, sql, status)
        else:
            sql = ('SELECT id,name,cup_type,status,created_on,finished_on '
                   'FROM cups ORDER BY created_on DESC')
            rows = yield self.dbController.dbRead(0, sql)
        defer.returnValue(rows)

    # ------------------------------------------------------------------
    # Participants
    # ------------------------------------------------------------------

    @defer.inlineCallbacks
    def addParticipant(self, cup_id, profile_id):
        sql = ("INSERT IGNORE INTO cup_participants (cup_id, profile_id, status) "
               "VALUES (%s, %s, 'active')")
        yield self.dbController.dbWrite(0, sql, cup_id, profile_id)
        defer.returnValue(True)

    @defer.inlineCallbacks
    def removeParticipant(self, cup_id, profile_id):
        sql = "DELETE FROM cup_participants WHERE cup_id=%s AND profile_id=%s"
        yield self.dbController.dbWrite(0, sql, cup_id, profile_id)
        defer.returnValue(True)

    @defer.inlineCallbacks
    def getCupParticipants(self, cup_id):
        """Returns list of (profile_id, name, points, status)."""
        sql = ('SELECT p.id, p.name, p.points, cp.status '
               'FROM cup_participants cp JOIN profiles p ON p.id=cp.profile_id '
               'WHERE cp.cup_id=%s ORDER BY p.points DESC')
        rows = yield self.dbController.dbRead(0, sql, cup_id)
        defer.returnValue(rows)

    # ------------------------------------------------------------------
    # Bracket
    # ------------------------------------------------------------------

    @defer.inlineCallbacks
    def activateCup(self, cup_id):
        """
        Transition cup from 'open' to 'active' and generate the first
        round of knockout matches.

        Participants are seeded by points (descending).  The bracket
        follows the standard highest-vs-lowest seeding pattern.
        If the number of participants is not a power-of-2, the top seeds
        receive automatic byes into the second round (recorded as
        'walkover' cup_matches with themselves as winner).
        """
        participants = yield self.getCupParticipants(cup_id)
        if len(participants) < 2:
            defer.returnValue(False)

        yield self.dbController.dbWriteInteraction(
            0, self._activateCupTxn, cup_id, participants)
        defer.returnValue(True)

    def _activateCupTxn(self, txn, cup_id, participants):
        txn.execute(
            "UPDATE cups SET status='active' WHERE id=%s", (cup_id,))

        n = len(participants)
        # find next power of 2
        bracket_size = 1
        while bracket_size < n:
            bracket_size *= 2

        num_byes = bracket_size - n
        # seeds with byes: top num_byes seeds skip first round
        seeded = [row[0] for row in participants]  # profile_ids sorted by points desc
        bye_seeds = seeded[:num_byes]
        playing_seeds = seeded[num_byes:]

        # first real round size
        first_round_size = len(playing_seeds) // 2
        # round label: number of matches at this stage
        first_round_label = bracket_size // 2

        # generate first-round matches: highest vs lowest remaining seed
        lo = len(playing_seeds) - 1
        for hi in range(first_round_size):
            home_id = playing_seeds[hi]
            away_id = playing_seeds[lo]
            txn.execute(
                'INSERT INTO cup_matches '
                '(cup_id, round, home_profile_id, away_profile_id, status) '
                'VALUES (%s,%s,%s,%s,"pending")',
                (cup_id, first_round_label, home_id, away_id))
            lo -= 1

        # bye seeds automatically advance to the second round
        # (they are placed in next-round slots; actual pairing happens when
        # the first round completes — see _advanceBracket)

    @defer.inlineCallbacks
    def getCupMatches(self, cup_id):
        sql = ('SELECT id,cup_id,match_id,round,home_profile_id,away_profile_id,'
               'winner_profile_id,status,played_on '
               'FROM cup_matches WHERE cup_id=%s ORDER BY round DESC, id ASC')
        rows = yield self.dbController.dbRead(0, sql, cup_id)
        defer.returnValue(rows)

    @defer.inlineCallbacks
    def getPendingCupMatch(self, profile_id_a, profile_id_b):
        """
        Return the pending cup_match row if these two profiles have
        an unplayed cup match together (in any active cup).
        """
        sql = ('SELECT cm.id, cm.cup_id, cm.round '
               'FROM cup_matches cm JOIN cups c ON c.id=cm.cup_id '
               'WHERE cm.status="pending" AND c.status="active" '
               'AND ((cm.home_profile_id=%s AND cm.away_profile_id=%s) '
               '  OR (cm.home_profile_id=%s AND cm.away_profile_id=%s)) '
               'LIMIT 1')
        rows = yield self.dbController.dbRead(
            0, sql, profile_id_a, profile_id_b, profile_id_b, profile_id_a)
        defer.returnValue(rows[0] if rows else None)

    @defer.inlineCallbacks
    def recordCupMatchResult(self, cup_match_id, match_id, winner_profile_id):
        """
        Record the outcome of a cup match and advance the bracket if the
        current round is now fully complete.
        """
        yield self.dbController.dbWriteInteraction(
            0, self._recordCupMatchTxn,
            cup_match_id, match_id, winner_profile_id)

    def _recordCupMatchTxn(self, txn, cup_match_id, match_id, winner_profile_id):
        from datetime import datetime
        txn.execute(
            'UPDATE cup_matches SET status="completed", match_id=%s, '
            'winner_profile_id=%s, played_on=%s WHERE id=%s',
            (match_id, winner_profile_id, datetime.now(), cup_match_id))

        # find cup_id and current round
        txn.execute(
            'SELECT cup_id, round FROM cup_matches WHERE id=%s',
            (cup_match_id,))
        row = txn.fetchall()
        if not row:
            return
        cup_id, current_round = row[0]

        # check if all matches in this round are done
        txn.execute(
            'SELECT count(*) FROM cup_matches '
            'WHERE cup_id=%s AND round=%s AND status="pending"',
            (cup_id, current_round))
        pending = txn.fetchall()[0][0]
        if pending > 0:
            return  # round not finished yet

        if current_round == 1:
            # final is done — cup is over
            txn.execute(
                "UPDATE cups SET status='finished', finished_on=%s WHERE id=%s",
                (datetime.now(), cup_id))
            # award winner/runner_up status
            txn.execute(
                'SELECT home_profile_id, away_profile_id, winner_profile_id '
                'FROM cup_matches WHERE cup_id=%s AND round=1',
                (cup_id,))
            final = txn.fetchall()[0]
            h, a, w = final
            loser = a if w == h else h
            txn.execute(
                "UPDATE cup_participants SET status='winner' "
                "WHERE cup_id=%s AND profile_id=%s", (cup_id, w))
            txn.execute(
                "UPDATE cup_participants SET status='runner_up' "
                "WHERE cup_id=%s AND profile_id=%s", (cup_id, loser))
            # award medals on profiles
            txn.execute(
                'SELECT cup_type FROM cups WHERE id=%s', (cup_id,))
            cup_type = txn.fetchall()[0][0]
            if cup_type == 'winnerscup':
                txn.execute(
                    'UPDATE profiles SET winnerscup_gold=winnerscup_gold+1 '
                    'WHERE id=%s', (w,))
                txn.execute(
                    'UPDATE profiles SET winnerscup_silver=winnerscup_silver+1 '
                    'WHERE id=%s', (loser,))
            else:
                txn.execute(
                    'UPDATE profiles SET competition_gold=competition_gold+1 '
                    'WHERE id=%s', (w,))
                txn.execute(
                    'UPDATE profiles SET '
                    'competition_silver=competition_silver+1 '
                    'WHERE id=%s', (loser,))
            return

        # generate next round: collect winners + bye seeds
        next_round = current_round // 2
        txn.execute(
            'SELECT winner_profile_id FROM cup_matches '
            'WHERE cup_id=%s AND round=%s ORDER BY id ASC',
            (cup_id, current_round))
        winners = [r[0] for r in txn.fetchall()]

        # also collect bye seeds (participants not yet in any match at this round)
        txn.execute(
            'SELECT profile_id FROM cup_participants WHERE cup_id=%s',
            (cup_id,))
        all_participants = {r[0] for r in txn.fetchall()}
        txn.execute(
            'SELECT home_profile_id, away_profile_id FROM cup_matches '
            'WHERE cup_id=%s', (cup_id,))
        played = {p for row in txn.fetchall() for p in row}
        bye_seeds = sorted(all_participants - played)  # sorted for determinism

        advancing = bye_seeds + winners

        # pair them: best bye + first winner, etc.
        lo = len(advancing) - 1
        for hi in range(len(advancing) // 2):
            home_id = advancing[hi]
            away_id = advancing[lo]
            txn.execute(
                'INSERT INTO cup_matches '
                '(cup_id, round, home_profile_id, away_profile_id, status) '
                'VALUES (%s,%s,%s,%s,"pending")',
                (cup_id, next_round, home_id, away_id))
            lo -= 1

    # ------------------------------------------------------------------
    # Manual walkover (admin override)
    # ------------------------------------------------------------------

    @defer.inlineCallbacks
    def walkover(self, cup_match_id, winner_profile_id):
        """Admin grants a walkover win to winner_profile_id."""
        yield self.dbController.dbWriteInteraction(
            0, self._recordCupMatchTxn,
            cup_match_id, None, winner_profile_id)

