"""Authored first-cohort note bodies for p_101 / p_103. Raw text is sanitized before publish."""

DEMO_NOTE_BODIES: dict[str, str] = {
    "p101-psych-consult-2026-09-12": (
        "Elisabeth Keller is a 65 year-old non-hispanic white female born 17 April 1961 "
        "(MRN-4471902). Psychiatric consult on ward 3B: persistent low mood after admission "
        "for glycemic control. Sertraline titrated. Suicide risk reviewed. Internal clinician "
        "note — not for the patient portal. Callback +41 44 555 01 17."
    ),
    "p101-admission-2026-09-10": (
        "Elisabeth Keller, 65 year-old non-hispanic white female born 1961-04-17, admitted "
        "10 September 2026 for glycemic control. Metformin continued. Discharge planning "
        "with ward 3B. Contact +41 44 555 01 17."
    ),
    "p103-cardiology-2026-05-20": (
        "Maria Santos is a 68 year-old female born 23 July 1958. Cardiology history and "
        "physical: essential hypertension on amlodipine. Next follow-up booked. "
        "Phone +41 22 555 03 23."
    ),
}

DEMO_NOTE_HINTS: dict[str, dict[str, tuple[str, ...]]] = {
    "p101-psych-consult-2026-09-12": {
        "names": ("Elisabeth Keller", "Elisabeth", "Keller"),
        "dob_strings": ("17 April 1961", "1961-04-17"),
        "mrns": ("MRN-4471902",),
        "phones": ("+41 44 555 01 17",),
        "source_ids": ("DocumentReference/p101-psych-consult-2026-09-12",),
    },
    "p101-admission-2026-09-10": {
        "names": ("Elisabeth Keller", "Elisabeth", "Keller"),
        "dob_strings": ("1961-04-17", "17 April 1961"),
        "mrns": ("MRN-4471902",),
        "phones": ("+41 44 555 01 17",),
        "source_ids": ("DocumentReference/p101-admission-2026-09-10",),
    },
    "p103-cardiology-2026-05-20": {
        "names": ("Maria Santos", "Maria", "Santos"),
        "dob_strings": ("23 July 1958", "1958-07-23"),
        "mrns": ("MRN-4471904",),
        "phones": ("+41 22 555 03 23",),
        "source_ids": ("DocumentReference/p103-cardiology-2026-05-20",),
    },
}
