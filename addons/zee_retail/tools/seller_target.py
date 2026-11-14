"""Pure helpers to split a monthly sales target between sellers (no Odoo import)."""
import calendar
from math import floor


def active_days_ratio(join_date, year, month):
    """Return `(total_days, active_days, ratio)` of a seller in the given month.

    A seller that joined before the month works all of it, one that joins later works none
    of it, and one that joins during the month works from the joining day included.
    """
    total_days = calendar.monthrange(year, month)[1]
    if not join_date or (join_date.year, join_date.month) < (year, month):
        return total_days, total_days, 1.0
    if (join_date.year, join_date.month) > (year, month):
        return total_days, 0, 0.0
    active_days = max(1, total_days - join_date.day + 1)
    return total_days, active_days, active_days / total_days


def distribute_target(total, ratios, method):
    """Split `total` between sellers and return `{key: target}` rounded to cents.

    :param total: the target of the whole group
    :param ratios: list of `(key, ratio)`, the share of the month each seller works
    :param method: `'prorated'` (weighted by ratio) or `'equal'`
    The shares always add up to `total` exactly: leftover cents go to the largest remainders.
    """
    if not ratios:
        raise ValueError("At least one seller is needed to distribute a target.")
    weights = [ratio for _key, ratio in ratios]
    if method == 'equal' or sum(weights) <= 0:
        weights = [1.0] * len(ratios)
    weight_sum = sum(weights)
    total_cents = round(total * 100)
    raw = [total_cents * weight / weight_sum for weight in weights]
    cents = [floor(share) for share in raw]
    leftover = total_cents - sum(cents)
    by_remainder = sorted(range(len(raw)), key=lambda i: (cents[i] - raw[i], i))
    for index in by_remainder[:leftover]:
        cents[index] += 1
    return {key: cents[i] / 100 for i, (key, _ratio) in enumerate(ratios)}
