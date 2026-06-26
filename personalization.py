"""Step 7 — personalization engine.

Ensures no two emails are byte-identical by varying surface features around the
rendered template body:

* greeting          ("Hi {name}," / "Hello {name}," / "Hey {name}," ...)
* closing / sign-off ("Best," / "Thanks," / "Cheers," ...)
* call-to-action    (varied phrasing, optionally reordered)
* light sentence/paragraph reordering of non-anchored paragraphs

A per-recipient :class:`random.Random` is seeded from the recipient's email (or
a configured global seed) so output is *stable per recipient* but *different
across recipients* — re-running the tool produces the same email for the same
person, which is what you want for idempotency.
"""
from __future__ import annotations

import hashlib
import random
from typing import Any, Optional

GREETINGS = [
    "Hi {name},",
    "Hello {name},",
    "Hey {name},",
    "Hi {name} —",
    "Dear {name},",
    "Hello {name} —",
]

CLOSINGS = [
    "Best",
    "Thanks",
    "Thank you",
    "Cheers",
    "Kind regards",
    "Best regards",
    "Appreciate your time",
    "Warm regards",
]

CTAS = [
    "Would you be open to a quick chat this week?",
    "Could you point me to the right person on the team?",
    "Would you be willing to refer me for the role?",
    "Is there a good time to connect briefly?",
    "I'd appreciate any guidance you can share.",
    "Would it be possible to forward my resume internally?",
    "Happy to share more if it'd be helpful.",
    "Let me know if a short call would work.",
]


class Personalizer:
    def __init__(
        self,
        vary_greeting: bool = True,
        vary_closing: bool = True,
        vary_sentence_order: bool = True,
        seed: Optional[int] = None,
    ):
        self.vary_greeting = vary_greeting
        self.vary_closing = vary_closing
        self.vary_sentence_order = vary_sentence_order
        self.global_seed = seed

    def rng_for(self, recipient_key: str) -> random.Random:
        """Deterministic RNG derived from the recipient (and optional seed)."""
        basis = f"{self.global_seed}:{recipient_key}" if self.global_seed is not None \
            else recipient_key
        digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()
        return random.Random(int(digest[:16], 16))

    # -- piece pickers (exposed so the assembler can use one RNG) -----------
    def greeting(self, name: str, rng: random.Random) -> str:
        if not self.vary_greeting:
            return f"Hi {name},"
        return rng.choice(GREETINGS).format(name=name)

    def closing(self, rng: random.Random) -> str:
        if not self.vary_closing:
            return "Best"
        return rng.choice(CLOSINGS)

    def cta(self, rng: random.Random) -> str:
        return rng.choice(CTAS)

    def personalize_body(self, body: str, rng: random.Random) -> str:
        """Apply light paragraph reordering to the *middle* paragraphs only.

        The first paragraph (hook) and last paragraph (ask/cta) are anchored;
        only the interior paragraphs are eligible for reordering so the email
        still reads coherently.
        """
        if not self.vary_sentence_order:
            return body
        paras = [p for p in body.split("\n\n")]
        if len(paras) <= 3:
            return body
        head, middle, tail = paras[0], paras[1:-1], paras[-1]
        rng.shuffle(middle)
        return "\n\n".join([head, *middle, tail])
