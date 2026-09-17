# Manual acceptance scenarios for GitHub issue #3.
# Boundary confirmed by the user on 2026-09-17: the seed-scope and
# generator-contract handoff. No application API or step runner exists yet.
# Readiness means the documented prerequisites are complete; it never starts
# generation, deploys services, publishes data, or proves runtime correctness.

Feature: An evidenced synthetic ingestion handoff
  The fixture and adapter implementers need approved scope and an inspected
  generator contract before they can begin the dependent implementation work.

  Scenario: The confirmed patient counts are preserved in the handoff
    Given the user approved 10 smoke patients and 100 seed patients on 2026-09-17
    When the reviewer reads the scope decision
    Then the smoke target is 10 patients
    And the seed target is 100 patients
    And those targets are distinguished from actual generated counts
    And the approval does not imply that either dataset has been generated

  Scenario Outline: Patient counts alone do not complete the cohort decision
    Given the patient counts have been approved
    And all other required cohort decisions have evidence except <decision>
    When the reviewer assesses the cohort handoff
    Then the cohort handoff remains incomplete
    And <decision> is recorded as unresolved

    Examples:
      | decision                  |
      | note types                |
      | note language             |
      | resource coverage         |
      | date window               |
      | clinical success examples |

  Scenario: A proposal is not evidence of approval
    Given the plan proposes Patient, Condition, and Observation coverage
    And no user decision confirms that coverage
    When the reviewer assesses the scope decision
    Then resource coverage remains proposed
    And approval of the patient counts does not approve resource coverage

  Scenario: Missing generator identity prevents adapter handoff
    Given no note-generator project or API URL has been supplied
    When the reviewer assesses the generator contract
    Then the generator handoff remains incomplete
    And the missing URL is recorded
    And no generator or request parameters are selected by assumption

  Scenario Outline: A URL alone does not establish the generator contract
    Given the supplied generator project or API is accessible for inspection
    And every required contract topic has evidence except <topic>
    When the reviewer assesses the generator contract
    Then the generator handoff remains incomplete
    And the missing evidence for <topic> is recorded

    Examples:
      | topic                       |
      | request format              |
      | response format             |
      | licensing                   |
      | local or hosted operation   |
      | reproducibility controls    |
      | failure behavior            |
      | a retained synthetic example |

  Scenario: An unavailable private contract is left unresolved
    Given the supplied generator contract requires private access
    And an approved access mechanism is unavailable
    When the reviewer records the inspection outcome
    Then contract inspection remains incomplete
    And the access requirement is recorded without credentials
    And fabricated request or response examples are not accepted as evidence

  Scenario: Reproducibility limits are represented honestly
    Given the inspected generator documentation does not guarantee deterministic output
    When the reviewer records the generator's reproducibility controls
    Then the documented controls and limitations are cited
    And identical notes from repeated requests are not promised without evidence
    And any conflict with the agreed cohort success criteria remains unresolved

  Scenario: Only synthetic credential-free examples enter the handoff
    Given a proposed contract example contains a credential or real patient data
    When the reviewer assesses that example for retention
    Then the example is not added to the handoff
    And the example requirement remains incomplete until a synthetic credential-free example is available

  Scenario: Source research does not establish runtime readiness
    Given the handoff references the existing source and model contract research
    And no runtime checks have been performed for this handoff
    When the reviewer assesses the verification evidence
    Then the documentation findings retain their source references
    And embedding profile and vector checks remain unverified
    And live Qdrant collection and PostgreSQL schema checks remain unverified
    And Presidio evaluation remains unverified
    And static Compose validation is not described as a successful ingestion run

  Scenario: The handoff preserves the initial milestone boundaries
    Given the scope decision records batch-first synthetic ingestion
    When the reviewer assesses the exclusions
    Then DICOM and VLM ingestion are outside the initial milestone
    And production patient data are outside the initial milestone
    And upload UI and reranker implementation are outside the initial milestone
    And the clinical agent cannot invoke the planned ingestion worker

  Scenario: An unanswered adversarial-fixture choice remains explicit
    Given no decision includes or excludes synthetic adversarial fixtures
    When the reviewer assesses the scope handoff
    Then the adversarial-fixture decision is unresolved
    And silence is not recorded as approval to include those fixtures

  Scenario Outline: Either explicit adversarial-fixture choice can complete that decision
    Given the user chooses <choice>
    When the reviewer records the adversarial-fixture decision
    Then the handoff records <result>
    And that decision does not change the agreed clinical seed scope

    Examples:
      | choice  | result                                                    |
      | include | a separately labelled safe synthetic evaluation set       |
      | exclude | no adversarial evaluation set for this initial milestone   |

  Scenario: A complete issue handoff is ready for dependent planning and implementation
    Given all cohort decisions have explicit approval and clinical success examples
    And the supplied generator contract has evidence for every required topic
    And a synthetic credential-free example is retained
    And the existing research and outstanding runtime checks are referenced separately
    And batch-first scope, exclusions, and the adversarial-fixture decision are recorded
    And no contract limitation conflicts with the agreed scope
    When the reviewer checks issue 3 against its acceptance criteria
    Then the issue 3 handoff is ready
    And the Synthea fixture issue can use the approved scope
    And the note-adapter issue still requires its separate patient-identity prerequisite
    And readiness does not assert that the ingestion pipeline has executed successfully
