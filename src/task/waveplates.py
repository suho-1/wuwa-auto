"""Shared Waveplate spending policies for daily and domain tasks.

The Guidebook daily activity tracks up to 180 spent Waveplates, while the
regular Waveplate wallet can hold 240.  Keeping those two limits separate is
important: "finish the daily objective" and "avoid regular Waveplate overcap"
are different user intents.
"""

DAILY_ACTIVITY_WAVEPLATE_TARGET = 180
REGULAR_WAVEPLATE_CAP = 240


def daily_waveplate_quota(used_waveplates=0, *, burn_all=False):
    """Return the domain quota for a daily run.

    ``0`` is the domain engine's existing sentinel for "spend all regular
    Waveplates".  Positive values stop once the 180-Waveplate Guidebook
    objective has been satisfied.
    """
    if burn_all:
        return 0
    try:
        used = max(0, int(used_waveplates))
    except (TypeError, ValueError):
        used = 0
    return max(0, DAILY_ACTIVITY_WAVEPLATE_TARGET - used)


def should_spend_waveplates(*, daily_rewards_ready, used_waveplates=0,
                             burn_all=False):
    """Decide whether the daily routine should enter a Waveplate activity."""
    if burn_all:
        return True
    return (not daily_rewards_ready
            and daily_waveplate_quota(used_waveplates) > 0)


def verified_single_claim(before_regular, after_regular, before_reserve,
                          after_reserve, *, cost=40, regeneration_tolerance=1):
    """Verify one claim from observed wallets rather than optimistic click state.

    One regular Waveplate can regenerate during the challenge, so a 40-cost
    claim normally appears as a 39–40 decrease. A one-point upper tolerance is
    retained for OCR jitter. Reserve currency must remain exactly unchanged.
    """
    try:
        spent = int(before_regular) - int(after_regular)
        reserve_unchanged = int(before_reserve) == int(after_reserve)
        expected = int(cost)
        tolerance = max(0, int(regeneration_tolerance))
    except (TypeError, ValueError):
        return False
    return expected - tolerance <= spent <= expected + tolerance and reserve_unchanged


def can_start_waveplate_run(current, total, cost, quota):
    """Start a claim only when regenerated Waveplates can pay its full cost.

    ``total`` can include reserve Waveplate Crystal value. No current task has
    a separate, explicit reserve-currency consent control, so every automatic
    mode—including the 180 activity target—must ignore that extra balance.
    ``quota`` remains part of the interface because zero is the domain engine's
    burn-all sentinel, but it must never weaken this currency-safety rule.
    """
    try:
        return int(current) >= int(cost)
    except (TypeError, ValueError):
        return False
