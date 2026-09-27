"""Tech voice-note text for synthetic incidents (BUILD_SPEC.md Section 8.2).

The note answers "how did you fix it?", never "what went wrong" — the robot
already reported that from telemetry. Notes stay under ~15 seconds of speech,
vary by tech persona, and carry the messiness of real field capture: filler
words, partial information, and the occasional confidently wrong guess at a
root cause.

Section 8.2 suggests generating these with Claude. These are templated
instead, because the dataset has to be byte-reproducible from `--seed 7` and
generate in under a second; `generate_incidents.py --llm` swaps in real
Claude-written notes when an API key is available and reproducibility is not
the priority.

Two constraints the phrasing has to respect:

- The verbs here must be ones the extractor actually recognises as actions
  (see `_fallback_extract` in server/integrations/llm.py), or the resulting
  RepairRecord comes back with no steps.
- Whether a hip-bolt fix used threadlocker is load-bearing, not decorative:
  it is the fork that hidden pattern 3 turns on.
"""

from __future__ import annotations

import random

LEG_WORDS = {"fl": "front left", "fr": "front right", "rl": "rear left", "rr": "rear right"}

TECHS = ("Ali", "Syon", "Marisol", "Dev", "Keisha", "Tomas", "Priya", "Wes")

PERSONAS = ("terse", "chatty", "procedural", "rushed", "uncertain")

OPENERS = {
    "terse": ("",),
    "chatty": ("ok so ", "alright so ", "yeah so ", "right, "),
    "procedural": ("",),
    "rushed": ("", "quick one, "),
    "uncertain": ("not totally sure but ", "think i got it, ", ""),
}

# Primary fix phrasings per fault. Verbs are drawn from the extractor's
# action vocabulary so each clause survives into RepairRecord.fix.steps.
FIX_ACTIONS: dict[str, tuple[str, ...]] = {
    "knee_motor_weak": (
        "swapped the {leg} knee actuator",
        "replaced the {leg} knee actuator",
        "pulled the {leg} knee actuator and installed a new one",
    ),
    "knee_motor_overheat": (
        "swapped the {leg} knee actuator",
        "replaced the {leg} knee actuator",
        "replaced the {leg} knee motor",
    ),
    "foot_pad_worn": (
        "replaced the {leg} foot pad",
        "swapped the {leg} foot pad",
        "installed a new pad on the {leg} foot",
    ),
    "hip_bolts_loose": (
        "retightened the {leg} hip bolts",
        "retorqued the {leg} hip mount",
    ),
    "encoder_drift": (
        "recalibrated the {leg} encoders",
        "reset the encoder offset and recalibrated",
    ),
    "harness_intermittent": (
        "disconnected and reconnected the {leg} leg harness",
        "replaced the {leg} leg harness",
        "inspected the {leg} harness connector and reconnected it",
    ),
    "battery_sag": (
        "swapped the battery pack",
        "replaced the battery pack",
    ),
    "imu_bias": (
        "recalibrated the IMU",
        "reset the IMU bias and recalibrated",
    ),
}

PREP_STEPS = ("powered it down", "powered down first", "isolated the battery")

FOLLOW_STEPS = {
    "knee_motor_weak": ("recalibrated the encoders", "reconnected the harness"),
    "knee_motor_overheat": ("recalibrated the encoders", "let it cool then recalibrated"),
    "foot_pad_worn": ("cleaned the mount face",),
    "hip_bolts_loose": (),
    "encoder_drift": (),
    "harness_intermittent": ("checked continuity",),
    "battery_sag": ("reconnected and reset",),
    "imu_bias": (),
}

VERIFICATIONS = (
    "ran a stand cycle to verify",
    "ran a stand cycle, holding fine",
    "tested it, no errors",
    "verified with a stand cycle",
    "ran it, tracking looks clean now",
)

# Root causes the tech volunteers. The "wrong" list is deliberately plausible
# and deliberately not what the telemetry actually indicted.
ROOT_CAUSES = {
    "knee_motor_weak": ("old one had no torque left", "actuator was shot"),
    "knee_motor_overheat": ("old one was scorching", "it was running way too hot", "thing was cooking itself"),
    "foot_pad_worn": ("pad was worn right through", "no tread left on it"),
    "hip_bolts_loose": ("bolts had backed right off", "mount was loose"),
    "encoder_drift": ("encoder had drifted off zero",),
    "harness_intermittent": ("connector was backed out", "harness pin looked corroded"),
    "battery_sag": ("pack was sagging under load",),
    "imu_bias": ("imu was reading a tilt that wasn't there",),
}

WRONG_GUESSES = (
    "probably just heat",
    "might be a bad batch honestly",
    "think the harness is the real problem",
    "could be the surface out here chewing things up",
    "reckon it's just age on this one",
)

TIPS = {
    "knee_motor_overheat": ("check the lot label before you put the new one in",),
    "knee_motor_weak": ("check the lot label before you put the new one in",),
    "hip_bolts_loose": ("use threadlocker or it'll back off again",),
    "foot_pad_worn": ("check the other three while you're down there",),
}

THREADLOCKER_PHRASES = (
    "applied threadlocker this time",
    "put threadlocker on them",
    "used threadlocker on the bolts",
)


def pick_tech(rng: random.Random) -> tuple[str, str]:
    return rng.choice(TECHS), rng.choice(PERSONAS)


def build_note(
    rng: random.Random,
    *,
    fault_id: str,
    leg: str | None,
    persona: str,
    supplier_lot: str | None = None,
    mention_lot: bool = False,
    used_threadlocker: bool = False,
    wrong_guess: bool = False,
) -> str:
    """One tech's spoken account of how they fixed this incident."""
    leg_word = LEG_WORDS.get(leg or "", "")
    clauses: list[str] = []

    if persona == "procedural" or (persona != "rushed" and rng.random() < 0.28):
        clauses.append(rng.choice(PREP_STEPS))

    clauses.append(rng.choice(FIX_ACTIONS[fault_id]).format(leg=leg_word).replace("  ", " ").strip())

    if fault_id == "hip_bolts_loose" and used_threadlocker:
        clauses.append(rng.choice(THREADLOCKER_PHRASES))

    follow = FOLLOW_STEPS.get(fault_id, ())
    if follow and persona != "rushed" and rng.random() < 0.6:
        clauses.append(rng.choice(follow))

    if mention_lot and supplier_lot:
        clauses.append(rng.choice((
            f"old one was lot {supplier_lot}",
            f"that was a lot {supplier_lot} unit",
            f"checked the label, lot {supplier_lot}",
        )))

    if rng.random() < (0.35 if persona == "rushed" else 0.72):
        clauses.append(rng.choice(ROOT_CAUSES[fault_id]) if not wrong_guess else rng.choice(WRONG_GUESSES))

    if persona != "rushed" or rng.random() < 0.5:
        clauses.append(rng.choice(VERIFICATIONS))

    tips = TIPS.get(fault_id, ())
    if tips and rng.random() < 0.3:
        clauses.append(rng.choice(tips))

    opener = rng.choice(OPENERS[persona])
    if persona == "terse":
        # Clipped delivery: each clause lands as its own sentence.
        note = f"{opener}" + " ".join(f"{clause[0].upper()}{clause[1:]}." for clause in clauses)
    else:
        note = f"{opener}{', '.join(clauses)}."
    if persona in {"procedural", "terse"}:
        note = note[0].upper() + note[1:]
    return note
