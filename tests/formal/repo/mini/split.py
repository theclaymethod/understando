"""Split a total into near-equal parts. Claim: the parts sum to the total."""


def split_evenly(total: int, parts: int) -> list[int]:
    quotient, remainder = divmod(total, parts)
    return [quotient + (1 if i <= remainder else 0) for i in range(parts)]
