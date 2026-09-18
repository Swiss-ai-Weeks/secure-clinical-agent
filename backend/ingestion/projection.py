"""Nested, code-aware projection for the pinned synthetic fixture only.

No narrative, incoming coding display, identifier, extension or reference object
is copied through. The checked-in catalog supplies reviewed terminology text.
"""

from collections import Counter
from datetime import date, datetime
import hashlib
import math
from pathlib import Path
import re

from worker import BatchError, canonical, extract_bundle

FHIR = "http://terminology.hl7.org/CodeSystem/"
LOINC = "http://loinc.org"
SNOMED = "http://snomed.info/sct"
EXCLUDED = {"56799-0", "32624-9", "56051-6", "54899-0"}
TABLE = {"Patient": "patients", "Encounter": "encounters", "Condition": "conditions",
         "Observation": "observations"}


def enums():
    # Use the repository's canonical value sets, rather than a second enum list.
    sql = (Path(__file__).parents[1] / "deploy/patient360/sql/fhir/00-roles-extensions.sql").read_text()
    return {name: re.findall(r"'([^']*)'", values) for name, values in re.findall(
        r"CREATE FUNCTION clinical\.vs_(\w+)\(\).*?SELECT ARRAY\[(.*?)\]::text\[\]", sql, re.S)}


ENUMS = enums()


def enum(value, name, required=False):
    if value is None and not required:
        return None
    if value not in ENUMS[name]:
        raise BatchError("missing_or_invalid_" + name)
    return value


def temporal(value, year=False, day=False):
    if value is None:
        return None
    if not isinstance(value, str):
        raise BatchError("invalid_date")
    try:
        if re.fullmatch(r"\d{4}", value):
            if not year:
                raise ValueError()
            result = int(value)
        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            date.fromisoformat(value)
            if not (year or day):
                raise ValueError()
            result = int(value[:4]) if year else value
        else:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError()
            result = parsed.year if year else (value[:10] if day else value)
        return result
    except ValueError as error:
        raise BatchError("unsupported_date_precision") from error


def ordered(start, end, day=False):
    if start is not None and end is not None:
        left = date.fromisoformat(start) if day else datetime.fromisoformat(start.replace("Z", "+00:00"))
        right = date.fromisoformat(end) if day else datetime.fromisoformat(end.replace("Z", "+00:00"))
        if right < left:
            raise BatchError("reversed_clinical_interval")


def number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise BatchError("invalid_numeric_value")
    return value


class Projector:
    def __init__(self, registry, policy):
        self.registry = registry
        self.policy = policy
        self.catalog = {(x["system"], x["code"]): x for x in policy["concepts"]}
        self.skipped = Counter()

    def coding(self, concept, preferred=None, required=False):
        if concept is None:
            if required:
                raise BatchError("missing_required_coding")
            return None
        candidates = concept.get("coding", [])
        if not candidates:
            raise BatchError("uncoded_concept_requires_review")
        safe = []
        for candidate in candidates:
            key = (candidate.get("system"), candidate.get("code"))
            item = self.catalog.get(key)
            if item is None:
                raise BatchError("unreviewed_clinical_code")
            if item.get("exclude"):
                raise BatchError("excluded_code_in_clinical_concept")
            safe.append({"system": key[0], "code": key[1], "display": item["display"]})
        safe.sort(key=lambda c: c["system"] != preferred)  # stable source-order tie break
        return {"coding": safe}

    def coded_enum(self, concept, name, system, required=False):
        if concept is None:
            return enum(None, name, required), None
        codes = concept.get("coding", [])
        if len(codes) != 1 or codes[0].get("system") != system:
            raise BatchError("unsupported_enum_coding")
        value = enum(codes[0].get("code"), name, required)
        return value, {"coding": [{"system": system, "code": value}]}

    def categories(self, resource, name, system):
        values = resource.get("category", [])
        safe = [self.coded_enum(c, name, system, True) for c in values]
        return (safe[0][0] if safe else None), [c[1] for c in safe]

    def label(self, *concepts):
        rank = "NRV"
        confidentiality, sensitivity = "N", set()
        for concept in concepts:
            for c in (concept or {}).get("coding", []):
                item = self.catalog[(c["system"], c["code"])]
                if rank.index(item["confidentiality"]) > rank.index(confidentiality):
                    confidentiality = item["confidentiality"]
                sensitivity.update(item["sensitivity"])
        return {"confidentiality": confidentiality, "sensitivity": sorted(sensitivity)}

    @staticmethod
    def coding_columns(row, concept, prefix=""):
        coding = concept["coding"][0] if concept else {}
        if prefix in ("type_", "reason_"):
            names = (prefix + "code", prefix + "system", prefix + "display")
        else:
            names = (prefix + "code", prefix + "code_system", prefix + "display")
        for target, source in zip(names, ("code", "system", "display")):
            row[target] = coding.get(source)

    def excluded(self, concept):
        return any(c.get("system") == LOINC and c.get("code") in EXCLUDED
                   for c in concept.get("coding", []))

    def project(self, bundle, batch, bundle_path, bundle_hash):
        extract_bundle(bundle)
        entries = bundle["entry"]
        resources = {f'{e["resource"]["resourceType"]}/{e["resource"]["id"]}': e["resource"]
                     for e in entries}
        aliases = {}
        for e in entries:
            key = f'{e["resource"]["resourceType"]}/{e["resource"]["id"]}'
            for alias in (key, e.get("fullUrl", key)):
                if alias in aliases and aliases[alias] != key:
                    raise BatchError("ambiguous_reference")
                aliases[alias] = key
        patient = next(k for k in resources if k.startswith("Patient/"))
        patient_key, _ = self.registry.allocate(patient, patient)
        result = {table: [] for table in TABLE.values()}

        def resolve(ref, kind):
            key = aliases.get(ref.get("reference")) if isinstance(ref, dict) else None
            if key is None or resources[key]["resourceType"] != kind:
                raise BatchError("unresolved_or_wrong_type_reference")
            return key

        for source, r in resources.items():
            kind = r["resourceType"]
            if kind not in (*TABLE, "DocumentReference"):
                self.skipped[kind] += 1
                continue
            if kind != "Patient" and resolve(r.get("subject"), "Patient") != patient:
                raise BatchError("cross_patient_reference")
            encounter = None
            if kind in ("Condition", "Observation") and "encounter" in r:
                encounter = resolve(r["encounter"], "Encounter")
                if resolve(resources[encounter].get("subject"), "Patient") != patient:
                    raise BatchError("cross_patient_encounter")
            # Source security labels need an explicit merger before adoption.
            if r.get("meta", {}).get("security"):
                raise BatchError("source_security_labels_require_review")
            opaque, cite = self.registry.allocate(source, patient)
            self.registry.record(batch, source, hashlib.sha256(canonical(r)).hexdigest(), {
                "bundle": bundle_path, "bundle_sha256": bundle_hash,
                "patient_key": patient_key, "encounter_source": encounter,
                "version": r.get("meta", {}).get("versionId"), "opaque": opaque,
                "cite_id": cite,
            })
            if kind == "DocumentReference":
                for ref in r.get("context", {}).get("encounter", []):
                    target = resolve(ref, "Encounter")
                    if resolve(resources[target].get("subject"), "Patient") != patient:
                        raise BatchError("cross_patient_document_encounter")
                    self.registry.link(batch, source, "encounter", target)
                self.skipped["DocumentReference"] += 1
                continue
            row = {"patient_key": patient_key, "confidentiality": "N", "sensitivity": []}
            if kind != "Patient":
                row.update(id=opaque, cite_id=cite, source_id=source)
            if kind in ("Condition", "Observation"):
                row["encounter_id"] = self.registry.allocate(encounter, patient)[0] if encounter else None
            if kind == "Patient":
                self.patient(r, row)
            elif kind == "Encounter":
                self.encounter(r, row)
            elif kind == "Condition":
                self.condition(r, row)
            else:
                if self.excluded(r.get("code", {})):
                    self.skipped["excluded_observation"] += 1
                    continue
                self.observation(r, row)
                components = []
                used = set()
                for component in r.get("component", []):
                    if self.excluded(component.get("code", {})):
                        self.skipped["excluded_component"] += 1
                        continue
                    safe_code = self.coding(component.get("code"), LOINC, True)
                    c = safe_code["coding"][0]
                    # Documented schema suffix; reject same code across systems or
                    # repeated components rather than inventing positional identity.
                    if c["code"] in used or "#" in c["code"]:
                        raise BatchError("ambiguous_component_identity")
                    used.add(c["code"])
                    child_source = source + "#" + c["code"]
                    child_id, child_cite = self.registry.allocate(child_source, patient)
                    child = dict(row, id=child_id, cite_id=child_cite, source_id=child_source,
                                 parent_id=row["id"])
                    synthetic = {k: v for k, v in r.items() if k in (
                        "status", "category", "effectiveDateTime", "effectivePeriod", "issued")}
                    synthetic.update(component)
                    self.observation(synthetic, child)
                    # A component cannot lower a parent's labels.
                    child["confidentiality"] = max(row["confidentiality"], child["confidentiality"], key="NRV".index)
                    child["sensitivity"] = sorted(set(row["sensitivity"] + child["sensitivity"]))
                    self.registry.record(batch, child_source, hashlib.sha256(canonical(component)).hexdigest(),
                                         {"parent": source, "patient_key": patient_key, "opaque": child_id,
                                          "cite_id": child_cite, "bundle": bundle_path, "bundle_sha256": bundle_hash})
                    components.append({k: v for k, v in child["resource"].items() if k in (
                        "code", "valueQuantity", "valueCodeableConcept", "valueString", "valueBoolean",
                        "valueInteger", "interpretation", "referenceRange")})
                    result["observations"].append(child)
                if components:
                    row["resource"]["component"] = components
                # Parent JSON contains component values, so inherit their labels too.
                for child in result["observations"]:
                    if child.get("parent_id") == row["id"]:
                        row["confidentiality"] = max(row["confidentiality"], child["confidentiality"], key="NRV".index)
                        row["sensitivity"] = sorted(set(row["sensitivity"] + child["sensitivity"]))
            result[TABLE[kind]].append(row)
        return result

    def patient(self, r, row):
        birth = temporal(r.get("birthDate"), year=True)
        if birth is not None and not 1900 <= birth <= 2100:
            raise BatchError("birth_year_outside_schema")
        if "deceasedBoolean" in r and "deceasedDateTime" in r:
            raise BatchError("multiple_deceased_values")
        died = temporal(r.get("deceasedDateTime"), year=True)
        deceased = r.get("deceasedBoolean", died is not None)
        if type(deceased) is not bool or (died is not None and birth is not None and died < birth):
            raise BatchError("invalid_deceased_value")
        row.update(sex=enum(r.get("gender"), "administrative_gender"), birth_year=birth,
                   deceased=deceased, deceased_year=died)
        safe = {"resourceType": "Patient"}
        if row["sex"] is not None:
            safe["gender"] = row["sex"]
        if birth is not None:
            safe["birthDate"] = str(birth)
        if died is not None:
            safe["deceasedDateTime"] = str(died)
        elif "deceasedBoolean" in r:
            safe["deceasedBoolean"] = deceased
        row["resource"] = safe

    def encounter(self, r, row):
        status = enum(r.get("status"), "encounter_status", True)
        cls = r.get("class", {})
        if cls.get("system") != FHIR + "v3-ActCode":
            raise BatchError("invalid_encounter_class_system")
        code = enum(cls.get("code"), "encounter_class", True)
        types = [self.coding(c, SNOMED, True) for c in r.get("type", [])]
        reasons = [self.coding(c, SNOMED, True) for c in r.get("reasonCode", [])]
        safe = {"resourceType": "Encounter", "status": status,
                "class": {"system": FHIR + "v3-ActCode", "code": code}}
        row.update(status=status, **{"class": code}, dept=None)
        self.coding_columns(row, types[0] if types else None, "type_")
        self.coding_columns(row, reasons[0] if reasons else None, "reason_")
        period = {k: temporal(v) for k, v in r.get("period", {}).items() if k in ("start", "end")}
        row.update(started_at=period.get("start"), ended_at=period.get("end"))
        ordered(row["started_at"], row["ended_at"])
        if period: safe["period"] = period
        if types: safe["type"] = types
        if reasons: safe["reasonCode"] = reasons
        row.update(self.label(*types, *reasons), resource=safe)

    def condition(self, r, row):
        code = self.coding(r.get("code"), SNOMED)
        safe = {"resourceType": "Condition"}
        self.coding_columns(row, code)
        if code: safe["code"] = code
        for field, name, system in (("clinicalStatus", "condition_clinical_status", "condition-clinical"),
                                    ("verificationStatus", "condition_verification_status", "condition-ver-status")):
            value, concept = self.coded_enum(r.get(field), name, FHIR + system)
            row["clinical_status" if field == "clinicalStatus" else "verification_status"] = value
            if concept: safe[field] = concept
        category, cats = self.categories(r, "condition_category", FHIR + "condition-category")
        row["category"] = category
        if cats: safe["category"] = cats
        for field, target in (("onsetDateTime", "onset_date"), ("abatementDateTime", "abatement_date"),
                              ("recordedDate", "recorded_date")):
            row[target] = temporal(r.get(field), day=True)
            if field in r:
                temporal(r[field], day=True)
                safe[field] = r[field]
        if any(k.startswith(("onset", "abatement")) and k not in ("onsetDateTime", "abatementDateTime") for k in r):
            raise BatchError("unsupported_condition_date_choice")
        ordered(row["onset_date"], row["abatement_date"], day=True)
        row.update(self.label(code), resource=safe)

    def observation(self, r, row):
        code = self.coding(r.get("code"), LOINC, True)
        self.coding_columns(row, code)
        status = enum(r.get("status"), "observation_status", True)
        category, cats = self.categories(r, "observation_category", FHIR + "observation-category")
        safe = {"resourceType": "Observation", "status": status, "code": code}
        if cats: safe["category"] = cats
        if "effectiveDateTime" in r and "effectivePeriod" in r:
            raise BatchError("multiple_effective_values")
        if any(k.startswith("effective") and k not in ("effectiveDateTime", "effectivePeriod") for k in r):
            raise BatchError("unsupported_effective_choice")
        effective = temporal(r.get("effectiveDateTime"))
        if effective: safe["effectiveDateTime"] = effective
        if "effectivePeriod" in r:
            period = {k: temporal(v) for k, v in r["effectivePeriod"].items() if k in ("start", "end")}
            ordered(period.get("start"), period.get("end"))
            safe["effectivePeriod"] = period
            effective = period.get("start")
        issued = temporal(r.get("issued"))
        if issued: safe["issued"] = issued
        row.update(status=status, category=category, effective_at=effective, issued_at=issued,
                   parent_id=row.get("parent_id"), value_num=None, unit=None, value_code=None,
                   value_code_system=None, value_display=None, value_text=None, value_bool=None,
                   interpretation=None, ref_low=None, ref_high=None, ref_text=None)
        choices = [k for k in r if k.startswith("value")]
        if len(choices) > 1:
            raise BatchError("multiple_observation_values")
        value_concept = None
        if choices:
            field = choices[0]
            value = r[field]
            if field == "valueQuantity":
                if value.get("comparator") is not None:
                    raise BatchError("quantity_comparator_requires_review")
                row["value_num"] = number(value.get("value"))
                unit = value.get("code", value.get("unit"))
                if unit is not None and unit not in self.policy["units"]:
                    raise BatchError("unreviewed_unit")
                if value.get("system") not in (None, "http://unitsofmeasure.org"):
                    raise BatchError("unsupported_unit_system")
                row["unit"] = unit
                safe[field] = {"value": row["value_num"]}
                if unit is not None:
                    safe[field].update(code=unit, unit=unit)
                    if value.get("system"): safe[field]["system"] = value["system"]
            elif field == "valueCodeableConcept":
                value_concept = self.coding(value, required=True)
                self.coding_columns(row, value_concept, "value_")
                safe[field] = value_concept
            elif field == "valueInteger":
                if type(value) is not int: raise BatchError("invalid_integer_value")
                row["value_num"] = value
                safe[field] = value
            elif field == "valueBoolean":
                if type(value) is not bool: raise BatchError("invalid_boolean_value")
                row["value_bool"] = value
                safe[field] = value
            elif field == "valueString":
                c = code["coding"][0]
                allowed = self.catalog[(c["system"], c["code"])].get("safe_strings", [])
                if value in allowed:
                    row["value_text"] = value
                    safe[field] = value
                else:
                    self.skipped["unapproved_valueString"] += 1
            else:
                raise BatchError("unsupported_observation_value_choice")
        if r.get("dataAbsentReason"):
            # No schema slot; absence stays NULL and is counted, never invented.
            self.skipped["dataAbsentReason"] += 1
        if r.get("interpretation"):
            concepts = []
            for item in r["interpretation"]:
                cs = item.get("coding", [])
                if len(cs) != 1 or cs[0].get("system") != FHIR + "v3-ObservationInterpretation" or cs[0].get("code") not in (
                    "N", "A", "AA", "H", "HH", "L", "LL", "POS", "NEG", "IND", "S", "R", "I"):
                    raise BatchError("unsupported_interpretation")
                concepts.append({"coding": [{"system": cs[0]["system"], "code": cs[0]["code"]}]})
            row["interpretation"] = concepts[0]["coding"][0]["code"]
            safe["interpretation"] = concepts
        ranges = []
        for rr in r.get("referenceRange", []):
            projected = {}
            for side in ("low", "high"):
                if side in rr:
                    bound = rr[side]
                    if bound.get("code", bound.get("unit")) not in (None, row["unit"]):
                        raise BatchError("reference_range_unit_mismatch")
                    projected[side] = {"value": number(bound.get("value"))}
            low, high = projected.get("low", {}).get("value"), projected.get("high", {}).get("value")
            if low is not None and high is not None and high < low:
                raise BatchError("reversed_reference_range")
            if projected: ranges.append(projected)
            if rr.get("text"): self.skipped["referenceRange_text"] += 1
        if ranges:
            safe["referenceRange"] = ranges
            row["ref_low"] = ranges[0].get("low", {}).get("value")
            row["ref_high"] = ranges[0].get("high", {}).get("value")
        row.update(self.label(code, value_concept), resource=safe)
