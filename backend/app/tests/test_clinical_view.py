from patient360.clinical_view import clean_synthea_name, clean_synthea_note, drop_social_sentences
from patient360.vault import Identity


def test_clean_synthea_name_strips_generator_digits():
    assert clean_synthea_name("Jerold208 Michel472") == "Jerold Michel"
    assert clean_synthea_name("Schiller186") == "Schiller"
    assert clean_synthea_name("Elisabeth") == "Elisabeth"


PNEUMONIA_TEMPLATE = """
Alex is a 21 year-old nonhispanic white male. Patient has a history of acute bronchitis (disorder),
severe anxiety (panic) (finding), disorder of teeth and/or supporting structures (disorder),
acute viral pharyngitis (disorder), gingivitis (disorder),
suspected disease caused by severe acute respiratory coronavirus 2 (situation).
Patient is presenting with pneumonia (disorder), hypoxemia (disorder).
Patient has never smoked. Patient identifies as heterosexual.
The following procedures were conducted:
- plain x-ray of chest
- oxygen administration by mask
- placing subject in prone position
The following lab reports were completed:
- CBC panel - blood by automated count
- CBC auto differential panel - blood
- Comprehensive metabolic 2000 panel - serum or plasma
- iron panel
- Troponin I.cardiac - serum or plasma by high sensitivity method
- PT panel - platelet poor plasma by coagulation assay
- serum or plasma iron panel
- platelet poor plasma by coagulation assay The patient was prescribed the following medications:
- 0.4 ML Enoxaparin sodium 100 MG/ML Prefilled Syringe
- Acetaminophen 500 MG Oral Tablet
- acetaminophen
No Known Allergies.
"""


def test_clean_synthea_note_keeps_pneumonia_and_drops_template_leftovers():
    cleaned = clean_synthea_note(PNEUMONIA_TEMPLATE)
    lowered = cleaned.lower()
    assert "21-year-old male" in lowered
    assert "pneumonia" in lowered
    assert "hypoxemia" in lowered
    assert "oxygen by mask" in lowered
    assert "enoxaparin 40 mg" in lowered
    assert "the patient was" not in lowered
    assert "blood by automated count" not in lowered
    assert "serum or plasma" not in lowered
    assert "platelet poor plasma" not in lowered
    history = next(line for line in cleaned.splitlines() if line.startswith("History:"))
    assert "CBC" not in history
    assert "CMP" not in history
    meds = next(line for line in cleaned.splitlines() if line.startswith("Medications:"))
    assert "presenting" not in meds.lower()
    assert "never smoked" not in lowered
    assert "heterosexual" not in lowered


def test_clean_synthea_note_drops_a_social_only_chunk():
    raw = (
        "The patient has never smoked, identifies as heterosexual, comes from a high "
        "socioeconomic background, has completed some college courses, and currently has Humana insurance."
    )
    cleaned = clean_synthea_note(raw).lower()
    assert "never smoked" not in cleaned
    assert "heterosexual" not in cleaned
    assert "socioeconomic" not in cleaned
    assert "college" not in cleaned
    assert "humana" not in cleaned


def test_drop_social_sentences_keeps_a_cited_blood_pressure():
    raw = (
        "The patient has never smoked and currently has Humana insurance - "
        "Systolic BP: 130 mmHg [obs_sbp] - Diastolic BP: 80 mmHg [obs_dbp]"
    )
    cleaned = drop_social_sentences(raw)
    lowered = cleaned.lower()
    assert "never smoked" not in lowered
    assert "humana" not in lowered
    assert "130 mmHg" in cleaned
    assert "80 mmHg" in cleaned


def test_identity_banner_uses_cleaned_synthea_names():
    ident = Identity.from_record(
        "p_b1ef4e59dd984d828f102e37a3a5cd77",
        {
            "given_name": "Jerold208 Michel472",
            "family_name": "Schiller186",
            "birth_date": "1991-01-28",
            "sex": "male",
            "mrn": "mrn",
        },
    )
    banner = ident.banner()
    assert banner["given_name"] == "Jerold Michel"
    assert banner["family_name"] == "Schiller"
