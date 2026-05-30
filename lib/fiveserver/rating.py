import math


ELO_DEFAULT = 1000
ELO_K = 32          # max points exchanged per match
ELO_MAX = 9999      # cap so it fits in a !H (unsigned short, max 65535)


def computeElo(home_rating, away_rating, home_score, away_score):
    """
    Standard Elo update for a single match.

    Returns (new_home_rating, new_away_rating).

    result from home perspective: 1 = win, 0.5 = draw, 0 = loss.
    """
    expected_home = 1.0 / (1.0 + 10 ** ((away_rating - home_rating) / 400.0))
    expected_away = 1.0 - expected_home

    if home_score > away_score:
        actual_home, actual_away = 1.0, 0.0
    elif home_score < away_score:
        actual_home, actual_away = 0.0, 1.0
    else:
        actual_home, actual_away = 0.5, 0.5

    new_home = int(round(home_rating + ELO_K * (actual_home - expected_home)))
    new_away = int(round(away_rating + ELO_K * (actual_away - expected_away)))

    new_home = max(0, min(ELO_MAX, new_home))
    new_away = max(0, min(ELO_MAX, new_away))
    return new_home, new_away


class RatingMath:
    """
    Utility class used to calculate user points, based
    on the user's "performance". The performance is currently
    computed as non-loosing percentage, with a draw
    being worth 1/3 of a win.


    For weights 0.44, 0.56, getPoints behaves like this:
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    vert: peformance, horiz: number of games

        |   5  10  50 100 200 1000
    ----+-------------------------
    0.00| 123 220 514 556 559 560
    0.10| 128 224 518 560 564 564
    0.20| 141 237 531 573 577 577
    0.30| 163 259 553 595 599 599
    0.40| 194 290 584 626 630 630
    0.50| 233 330 624 666 669 670
    0.60| 282 378 672 714 718 718
    0.70| 339 435 729 771 775 775
    0.80| 405 501 795 837 841 841
    0.90| 480 576 870 912 916 916
    1.00| 563 660 954 996 999 1000
    """

    def __init__(self, w1, w2):
        """
        w1 and w2 must be normalized weights
        (meaning: w1+w2 = 1.0)
        """
        self.w1 = w1
        self.w2 = w2

    def getScore(self, perf, num_games):
        return self.w2 + self.w1*perf*perf + self.w2*(
            -math.exp(-num_games*0.05))

    def getPoints(self, stats):
        num_games = stats.wins + stats.draws + stats.losses
        if num_games == 0:
            perf = 0.0
        else:
            perf = (stats.wins + 0.333*stats.draws)/num_games
        return int(1000*self.getScore(perf, num_games))

    def getDivision(self, points):
        """
        Calculate division, based on number of points
        """
        for division, threshold in enumerate([250,450,600,750]):
            if points < threshold:
                return division
        return 4

