"""A small loop: call an operation until it succeeds, fails for good, or the tries run out."""

from collections.abc import Sequence


def retry(outcomes: Sequence[str], max_tries: int) -> tuple[str, int]:
    """``outcomes[i]`` is the result of call ``i``: "ok", "transient" or "fatal".
    Returns the final result and the number of calls made."""
    tries = 0
    while tries < max_tries:
        outcome = outcomes[tries]
        tries += 1
        if outcome == "ok":
            return "ok", tries
        if outcome == "fatal":
            return "fatal", tries
    return "gave_up", tries
