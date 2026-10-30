"""The seed guard: the code itself refuses a sealed seed, so seed-blindness is not something a person has to remember.

Two blocks of seeds belong to the sealed acceptance lab: the LIVE block (7,000,101 to 7,000,140, the 40 acceptance campaigns) and the RETIRED block (7,000,001 to 7,000,040, used before the first seal and
never to be used for acceptance again). Nothing in the development lab, the development comparison or any smoke-test path may be given a seed from either block: `refuse_sealed_seed` raises at once.
Only the official acceptance runner may pass a LIVE seed, and only by wrapping it in `AcceptanceSeed` on purpose, which the code that takes seeds for acceptance (the engine's strategies) may accept and
the development lab never does. A retired seed is refused everywhere, wrapped or not. A static check (check_seal.bat) fails if `AcceptanceSeed` is named anywhere but this file and the acceptance folder.
"""
from __future__ import annotations

LIVE_BLOCK = (7_000_101, 7_000_140)
RETIRED_BLOCK = (7_000_001, 7_000_040)
SEALED_BLOCKS = (RETIRED_BLOCK, LIVE_BLOCK)


class SealedSeedError(Exception):
    """A sealed acceptance seed was given to something that is not the official acceptance runner."""


class AcceptanceSeed(int):
    """A live acceptance seed, wrapped on purpose by the official acceptance runner. Anything else must never create one."""


def in_sealed_block(seed) -> bool:
    value = int(seed)
    return any(lo <= value <= hi for lo, hi in SEALED_BLOCKS)


def refuse_sealed_seed(seed, where: str, allow_acceptance: bool = False) -> None:
    """Raise SealedSeedError if `seed` is inside either sealed block. `allow_acceptance` lets an `AcceptanceSeed` from the LIVE block through, for code the acceptance runner drives; the development lab
    never sets it, and a retired seed is never let through."""
    value = int(seed)
    if not in_sealed_block(value):
        return
    if allow_acceptance and isinstance(seed, AcceptanceSeed) and LIVE_BLOCK[0] <= value <= LIVE_BLOCK[1]:
        return
    block = "the retired block 7,000,001 to 7,000,040" if RETIRED_BLOCK[0] <= value <= RETIRED_BLOCK[1] else "the live block 7,000,101 to 7,000,140"
    raise SealedSeedError(f"Seed {value} is inside a sealed acceptance block ({block}), so {where} refuses it. Sealed seeds are only ever used by the official acceptance runner. "
                          "Use a development seed (10000 and up, outside 10200 to 10239 until the comparison has been run).")
