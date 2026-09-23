---
name: patient360-tools
description: Query authorized Patient360 labs, medications, conditions, encounters, allergies, diet, imaging, notes, and de-identified counts. Use for any clinical question about a patient_key. Calls POST /tools/query, POST /tools/notes, and POST /tools/imaging with a placeholder bearer. When the user asks to segment CT anatomy, include classes on imaging.
---

# Patient360 tools

Retrieve only what the backend authorizes. Never invent values. Never print tokens. Never request pixels or media URLs.

Base URL: `http://host.openshell.internal:8088`

Authorization header must be exactly:

`Authorization: Bearer openshell:resolve:env:RUN_TOKEN`

The gateway substitutes the real run token at egress. If you see the placeholder in a response, stop and report no authorized evidence.

## Query one chart

```bash
python3 /sandbox/.openclaw/workspace/skills/patient360-tools/p360_tools.py query '{"patient_key":"PKEY","dataset":"labs"}'
```

`dataset` is one of `labs`, `meds`, `conditions`, `encounters`, `allergies`, `diet`.

Optional `filters`: `since`, `until`, `code`, `category`, `active_only`. Use them to narrow a large result. A dataset the role may not read returns 404.

## Search notes

```bash
python3 /sandbox/.openclaw/workspace/skills/patient360-tools/p360_tools.py notes '{"patient_key":"PKEY","question":"QUESTION"}'
```

Use notes for narrative, summaries, and documents.

## Imaging

```bash
python3 /sandbox/.openclaw/workspace/skills/patient360-tools/p360_tools.py imaging '{"patient_key":"PKEY"}'
```

Studies, reports, and `allowed_classes` only. Report text or metadata depends on the role. Do not request pixels or `/media`. To list possible overlays, use this call, then write the answer in your own words from `allowed_classes`. Do not send `classes` for a catalog question.

When the user asks to segment or overlay a named organ on a CT, add those classes and the CT `orthanc_id` from the studies list:

```bash
python3 /sandbox/.openclaw/workspace/skills/patient360-tools/p360_tools.py imaging '{"patient_key":"PKEY","study_id":"ORTHANC_ID","classes":["heart"]}'
```

Allowed `classes` include `heart`, `liver`, `lung`, `kidney`, `spleen`, `aorta`, `pancreas`, `brain`, `trachea`, `bladder`, `stomach`. Unknown names are rejected. The backend checks pixel permission before VISTA runs. A 404 means this role cannot segment. The response is still text (`overlay_text`, report rows). Never ask for mask bytes.

## Counts

```bash
python3 /sandbox/.openclaw/workspace/skills/patient360-tools/p360_tools.py query '{"dataset":"conditions","aggregate":{"group_by":["code"],"measure":"count"}}'
```

Omit `patient_key`. `group_by` is a column such as `code`, `category`, `sex`, or `birth_year`. The result is a suppressed count, not one patient's chart. A 404 means this role cannot count.

A 404 means no authorized evidence. Cite `cite_id` values from the JSON. If a `cite_id` contains the patient key, cite `note_<the rest>` with hyphens changed to underscores. Do not mention this skill, the sandbox, or the token.
