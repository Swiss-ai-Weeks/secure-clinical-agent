# Patient360 — Frontend Product & UI Specification

## 1. Product Vision

Patient360 is a clinical workspace for private clinics that brings together patient-provided information, clinician-entered information, medical documents, longitudinal health data, and AI-assisted insights in one clear interface.

The frontend should make patient information:

* Fast to understand
* Easy to navigate
* Visually structured
* Accessible from a distance or by users with impaired eyesight
* Difficult to misinterpret
* Pleasant enough to use every day
* Clearly differentiated between recorded facts, patient-reported information, and AI-generated content

The primary experience is a **clinical staff dashboard** centered around a comprehensive **Patient 360 profile**.

A secondary patient-facing interface allows patients to submit and update their own information.

---

# 2. Core UX Principle

The application should answer:

> **“What do I need to know about this patient right now?”**

within approximately five seconds of opening a patient profile.

The system should avoid requiring clinicians to dig through many pages, dense tables, or unstructured notes to reconstruct a patient's current situation.

Important information should be surfaced immediately, while detailed historical data remains available underneath.

---

# 3. User Types

The system will eventually support different views and available actions depending on user permissions through an **Attribute-Based Access Control (ABAC)** system.

Examples may include:

* Physicians
* Nurses
* Clinical assistants
* Administrative staff
* Researchers
* Clinic management
* Patients

The exact ABAC policies and differences between roles are **TBD**.

The frontend should therefore be built so that:

* Individual cards can be hidden or displayed depending on permissions.
* Navigation items can be permission-dependent.
* Specific data fields can be redacted or unavailable.
* Actions can be disabled independently from data visibility.
* AI queries can inherit the user's permissions.

The initial frontend can use a generic **Clinical Staff** view.

---

# 4. Main Application Structure

The clinical application uses a persistent dashboard layout.

### Primary navigation

* Home
* Patients
* Tasks / Follow-ups
* Documents / Inbox
* Cohort Insights
* Audit & Privacy

Patient-specific pages additionally expose:

* Overview
* Timeline
* Labs
* Medications
* Documents
* Notes

A persistent **Ask Patient360** AI interaction should be available throughout the application.

---

# 5. Clinic Home — “Today”

The Home page acts as the clinician's daily command center.

It should prioritize actionable information rather than displaying generic statistics.

## Main sections

### Today's Patients

Large patient cards showing:

* Patient name
* Age
* Appointment time
* Appointment type
* Most relevant reason for visit
* Important warning or outstanding action
* Optional patient photo/avatar

Selecting a patient opens their Patient 360 profile.

---

### Morning Briefing

An AI-generated summary of clinically relevant developments.

Example:

> **Good morning, Dr. Müller**
>
> You have 8 patients today.
>
> 2 have new lab results.
>
> 1 patient reported worsening symptoms overnight.
>
> 3 follow-ups are overdue.

Each statement should link directly to the relevant patient or data.

---

### Needs Attention

A compact list of clinically relevant alerts.

Examples:

* New abnormal lab result
* Patient reports worsening symptoms
* Missing requested measurement
* Medication inconsistency
* Follow-up overdue
* New uploaded report waiting for review

Alerts should be prioritized and visually distinct without creating a stressful “everything is red” interface.

---

### Recent Patient Activity

A stream containing recent:

* Patient questionnaire submissions
* Uploaded documents
* Clinician updates
* Lab results
* Medication changes
* Symptom reports

---

# 6. Patients View

The Patients page provides both traditional navigation and AI-assisted discovery.

## Standard search

Users should be able to find patients using:

* Name
* Patient ID
* Date of birth
* Phone/email where permitted
* Condition
* Medication
* Assigned clinician

Filters may include:

* Assigned clinician
* Active/inactive
* Age
* Diagnosis
* Appointment status
* Recent activity

---

## Natural-Language Patient Search

The search experience should also demonstrate the application's RAG and AI capabilities.

Example queries:

> “Patients with diabetes who recently reported dizziness.”

> “Who was prescribed amoxicillin last month?”

> “Show patients with abnormal cholesterol results who have not been seen recently.”

The UI should clearly indicate when search results were generated through AI rather than ordinary filtering.

---

# 7. Patient 360

Patient 360 is the central screen of the application and should receive the highest level of visual polish.

The purpose of the page is to give a clinician an immediate understanding of the patient while making deeper information available without leaving the context of the patient.

---

## 7.1 Patient Header

The top of the page includes:

**Primary information**

* Full name
* Age
* Gender/sex where clinically relevant
* Patient ID
* Status
* Assigned clinician
* Optional profile photo/avatar

**Important information**

* Major allergies
* Blood type
* Major diagnoses
* Important risk indicators

Actions may include:

* Add information
* Add clinical note
* Upload document
* Start consultation
* Ask Patient360

Critical information such as severe allergies should be highly visible without relying solely on color.

---

# 8. AI Clinical Brief

One of the most prominent components of Patient 360 should be an AI-generated **Clinical Brief**.

Example:

> **✦ Clinical Brief**
>
> Emma's migraine frequency has increased from approximately once per month to three times per month since June.
>
> Her latest LDL measurement is elevated compared with her previous result.
>
> No neurological red flags have been documented.

AI-generated statements should never visually resemble raw clinical facts.

Each statement should be traceable to its source.

Possible interactions:

* View sources
* Expand explanation
* Regenerate summary
* Ask follow-up question

---

# 9. “Since Last Visit”

A highly visible card summarizes what has changed since the clinician last saw the patient.

Example:

> **Since your last consultation**
>
> **3** new symptom entries
> **1** new laboratory result
> LDL increased **12%**
> Patient reported starting magnesium
> No new allergies
> No medication changes

Every item should be clickable.

Clicking it opens the underlying information.

This feature is intended to demonstrate:

* Longitudinal reasoning
* Retrieval
* RAG
* Change detection
* Structured summarization

without forcing the user to interact with a chatbot.

---

# 10. Current Clinical Snapshot

A grid of large, easy-to-read cards shows current clinical information.

Possible cards include:

### Conditions

Current active diagnoses and relevant history.

### Medications

Current medications with:

* Name
* Dosage
* Frequency
* Start date

### Allergies

Clearly separated and prominently displayed.

### Latest measurements

Examples:

* Blood pressure
* Heart rate
* Weight
* BMI
* SpO₂
* Temperature

### Latest labs

Important recent laboratory values.

Abnormal values should be visibly marked.

Example:

**LDL Cholesterol**
4.2 mmol/L ↑
Previous: 3.7 mmol/L

### Things to Review

AI or rule-based identification of potentially relevant issues.

Examples:

* Elevated LDL
* Increasing migraine frequency
* Missing follow-up measurement

These are prompts for clinician review rather than diagnoses.

---

# 11. Patient Timeline

The timeline is one of the application's signature interactions.

It combines information from otherwise fragmented medical sources into one chronological history.

Timeline events can include:

* Consultations
* Clinical notes
* Patient-reported symptoms
* Questionnaires
* Medication changes
* Laboratory results
* Measurements
* Uploaded documents
* Imaging
* Diagnoses
* Procedures
* Referrals
* AI-processed documents

---

## Timeline interaction

Events should appear as large chronological cards rather than a dense table.

Example:

**12 September — Consultation**

Migraine frequency increased to approximately three episodes per month.

`Dr. Müller` `Consultation`

---

**2 September — Patient update**

Reported headaches on four of the previous seven days.

`Patient reported`

---

**18 August — Laboratory result**

LDL cholesterol: **4.2 mmol/L ↑**

`Laboratory`

---

## Timeline filters

Users can filter by:

* All
* Visits
* Labs
* Medications
* Patient updates
* Documents
* Notes

Filters should behave like large pills/tabs and be easily clickable.

The default should remain **All**.

---

# 12. Labs View

The Labs section provides both current values and historical trends.

Each metric should support:

* Current result
* Reference range
* Previous result
* Date
* Trend
* Historical graph
* Source

Graphs should emphasize readability rather than visual decoration.

AI actions may include:

* ✦ Explain trend
* ✦ Compare with previous results
* ✦ Find related history

Any AI interpretation must be explicitly labeled as such.

---

# 13. Medications View

Current and historical medication information should be clearly separated.

For each medication:

* Name
* Dosage
* Frequency
* Route where relevant
* Start date
* Stop date if applicable
* Prescribing clinician
* Reason if known

Medication history should make starts, dosage changes, and discontinuations easy to identify.

Possible AI interaction:

> ✦ “Summarize changes to this patient's medication over the last six months.”

---

# 14. Documents

Documents may include:

* External medical reports
* Laboratory reports
* Imaging reports
* Referral letters
* Prescriptions
* PDFs
* Patient uploads
* Images

The Documents interface should display:

* Document type
* Date
* Source
* Processing state
* Who uploaded it

---

## AI Document Processing

When a new document is uploaded, AI may extract structured information.

Example:

> **Information detected**
>
> Diagnosis: Iron-deficiency anemia
> Medication: Ferrous sulfate 200 mg
> Follow-up: Blood test in 8 weeks

The extracted information should **not automatically become canonical patient information**.

The UI should allow a clinician to:

* Accept
* Edit
* Reject

each extracted item.

---

# 15. Notes

Clinicians can create and view clinical notes.

Possible AI assistance:

* ✦ Summarize note
* ✦ Convert to structured fields
* ✦ Extract follow-up tasks
* ✦ Draft consultation summary
* ✦ Find previous related notes

Original text should always remain accessible.

---

# 16. Ask Patient360

AI should be integrated throughout the product rather than existing only as a separate chatbot.

A persistent **Ask Patient360** control opens an AI side panel.

When inside a patient profile, the AI automatically understands that patient's context.

Example questions:

> “What changed since Emma's previous visit?”

> “Why was metformin stopped?”

> “Summarize her cardiovascular history.”

> “When did these headaches first appear?”

> “Has she previously reported similar symptoms?”

Answers should contain citations linking directly to source records.

Selecting a citation should reveal the underlying timeline entry, document, lab result, or note.

---

# 17. Clinic-Level AI

When Patient360 is opened outside an individual patient profile, the AI can operate at clinic level according to the user's permissions.

Example questions:

> “Which of my patients have outstanding blood tests?”

> “Which patients have reported worsening symptoms this week?”

> “How many hypertensive patients have not had blood pressure measured in six months?”

Results should combine:

* Plain-language answer
* Relevant numbers
* Optional chart
* Underlying patient list

This interaction can power the Cohort Insights view.

---

# 18. Tasks & Follow-Ups

Tasks can be created manually or suggested from clinical data.

Examples:

* Repeat blood test in three months
* Call patient regarding MRI result
* Review newly uploaded report
* Schedule follow-up consultation

Each task includes:

* Patient
* Description
* Due date
* Assignee
* Priority
* Status
* Source

AI-generated tasks must be clearly marked and require confirmation before becoming active.

---

# 19. Audit & Privacy

Because privacy is central to Patient360, the application should make security visible.

Possible audit information:

* Who viewed a patient
* What information was accessed
* When the access occurred
* What AI queries were performed
* Which sources an AI response accessed
* Whether an access request was blocked

Example:

**17:04 — Dr. Müller**
Viewed Emma Laurent → Laboratory results

**16:52 — AI Assistant**
Accessed 3 records to answer clinical query

**16:44 — Access denied**
Restricted document requested

This section can later reflect the ABAC model.

---

# 20. Patient Portal

The patient-facing application should be considerably simpler than the clinical dashboard.

Its main purposes are:

* Enter personal information
* Complete health questionnaires
* Maintain medication information
* Maintain allergy information
* Report symptoms
* Enter measurements
* Upload documents
* Respond to clinic requests
* View submitted information

The patient should not be exposed to unnecessary clinical complexity.

---

# 21. Information Provenance

The interface must clearly differentiate information according to its origin.

## Clinical / recorded information

Default interface styling.

Example:

**LDL cholesterol**
4.2 mmol/L

---

## Patient-reported information

Clearly marked.

Example:

`Patient reported`

Headaches on 4 of the last 7 days.

A subtle pink treatment can be used.

---

## AI-generated information

Always identifiable using a consistent symbol:

**✦**

Example:

**✦ Clinical Brief**

AI-generated information should preferably use a light-yellow card treatment.

AI content must never visually masquerade as clinician-entered medical information.

---

# 22. Visual Design System

## Overall character

The interface should feel:

* Warm
* Friendly
* Calm
* Human
* Modern
* Slightly playful
* Extremely clear

It may be somewhat **cutesy**, but must never feel childish or undermine the seriousness of clinical information.

The goal is:

> **“A healthcare dashboard people actually enjoy looking at.”**

rather than a traditional hospital information system.

---

# 23. Color Direction

The primary visual palette uses **light yellow and pink**.

Suggested direction:

### Background

Warm off-white / very pale yellow.

Example character:

`#FFFDF4`

---

### Primary yellow

Soft buttery yellow.

Used for:

* AI cards
* Selected elements
* Highlights
* Large background areas

Approximate direction:

`#FFEFA8`

---

### Pink

Warm soft pink.

Used for:

* Interactive accents
* Patient-reported information
* Selected navigation
* Buttons
* Decorative details

Approximate direction:

`#F6B8C8`

---

### Text

Very dark plum or charcoal rather than pure black.

Approximate direction:

`#28232A`

---

Clinical status colors such as red, orange, or green should be introduced only where they communicate actual meaning.

Color should **never be the sole carrier of clinical information**.

---

# 24. Shape Language

Cards and controls use noticeably rounded corners.

Suggested radius:

* Small controls: 10–12 px
* Buttons: 12–16 px
* Cards: 18–24 px
* Large panels: 24–32 px

Avoid excessive use of:

* Sharp rectangles
* Thin borders
* Tiny controls
* Dense spreadsheet-style grids

Cards should feel soft but remain clearly separated.

---

# 25. Typography

Readability is a primary design requirement.

Clinical users may:

* Have reduced eyesight
* Be tired
* View the screen from a distance
* Work under time pressure
* Scan rather than read carefully

Therefore:

### Body text

Approximately **16–18 px minimum**.

### Secondary information

Avoid text smaller than approximately **14 px** unless unavoidable.

### Patient name

Approximately **28–36 px**.

### Major metrics

Approximately **28–40 px**.

### Page titles

Approximately **30–40 px**.

Important information should use size and weight hierarchy rather than relying exclusively on color.

---

# 26. Interaction Size

Clickable targets should be generous.

Buttons, pills, tabs, and filters should not require precise mouse positioning.

Suggested minimum height:

**44–48 px**

Frequently used actions may be larger.

---

# 27. Clarity Over Minimalism

The interface should not pursue minimalism at the expense of understanding.

Avoid ambiguous icon-only actions such as:

`⋮`

when an explicit label would be clearer.

Prefer:

**Add note**

instead of an unlabeled pencil icon.

Prefer:

**Upload document**

instead of an isolated upload symbol.

Icons may reinforce labels but should rarely replace them.

---

# 28. Accessibility Principles

The interface should aim for:

* Strong contrast
* Large default typography
* Large click targets
* Keyboard accessibility
* Clear focus states
* Screen-reader-friendly labels
* Information communicated through text and icons as well as color
* Reduced dependence on hover interactions
* No essential actions hidden behind tiny menus

Important medical information should remain readable even at increased browser zoom.

Layouts should tolerate approximately **125–150% zoom** without breaking.

---

# 29. Visual Density

The application should be information-rich but not visually dense.

Use:

* Generous spacing
* Card grouping
* Strong visual hierarchy
* Progressive disclosure
* Tabs and expansion where appropriate

Avoid placing every possible medical field on the initial Patient 360 screen.

The Overview should contain only information relevant to quickly understanding the patient's current state.

Detailed information belongs one interaction deeper.

---

# 30. AI Interaction Language

AI should feel like an assistant embedded in the clinical workflow rather than a separate chatbot product.

Use small contextual actions such as:

**✦ Summarize**

**✦ Explain trend**

**✦ Compare with last visit**

**✦ Find related history**

**✦ Draft note**

**✦ Ask Patient360**

The ✦ symbol becomes a consistent visual language indicating:

> “AI is helping here.”

---

# 31. Loading & AI Processing States

AI interactions may take longer than normal UI interactions.

Instead of generic spinners, the interface can provide meaningful status messages:

> Searching Emma's clinical history…

> Comparing her previous laboratory results…

> Reading 4 relevant documents…

> Preparing summary…

This makes the system feel transparent while communicating that retrieval is occurring.

---

# 32. Empty States

Empty states should be friendly and explicit.

Instead of:

> No data.

Use:

> **No laboratory results yet**
>
> Lab results added by your clinic or uploaded by the patient will appear here.

Where appropriate, provide an action:

**Upload lab result**

---

# 33. Error Prevention

Because the application contains clinical information, potentially destructive or consequential actions should require additional clarity.

Examples:

Deleting a note:

> **Delete this clinical note?**
>
> This will remove it from the active patient record.

AI-extracted information:

> **Add these 3 items to Emma's medical record?**

Medication changes should clearly distinguish between:

* Editing the digital record
* Recording that a medication was discontinued
* Actually prescribing/changing treatment

The interface should avoid language that makes these actions ambiguous.

---

# 34. Demo Priority

For the hackathon, frontend development should prioritize a highly polished vertical slice rather than implementing every screen with equal depth.

## Priority 1 — Patient 360

Build extremely well:

* Patient header
* Clinical Brief
* Since Last Visit
* Current snapshot
* Timeline
* Ask Patient360

---

## Priority 2 — Clinic Home

Build:

* Today's patients
* Morning Briefing
* Needs Attention
* Recent patient activity

---

## Priority 3 — AI Interactions

Demonstrate:

* Ask a patient-specific question
* Source citations
* Natural-language patient search
* AI summary
* Change detection

---

## Priority 4 — Supporting Screens

Create convincing versions of:

* Patients
* Labs
* Medications
* Documents
* Cohort Insights
* Tasks
* Audit & Privacy

Not every feature needs complete backend functionality for the hackathon demo.

---

# 35. Signature Demo Experience

The ideal demo sequence is:

1. Clinician opens Patient360.

2. Home dashboard immediately highlights something requiring attention.

3. Clinician opens **Emma Laurent**.

4. Patient 360 instantly displays:

   * Important clinical context
   * Two items requiring review
   * Latest measurements
   * AI Clinical Brief

5. **Since Last Visit** explains exactly what changed.

6. Clinician opens the Timeline and sees information from:

   * Consultations
   * Patient reports
   * Labs
   * Documents

7. Clinician asks:

   > “What changed with Emma's migraines over the last six months?”

8. Patient360 searches the record and produces a concise answer.

9. Clicking the AI answer's citations highlights the actual source events in the timeline.

10. Clinician uploads a new medical report.

11. AI extracts several structured facts.

12. Clinician approves the relevant ones.

13. Patient 360 updates immediately.

The result should make it obvious that Patient360 is not merely a chatbot connected to medical records.

It is an **AI-native interface for understanding a patient's entire clinical history.**
