//! Same `evaluate(subject, resource, context, check)` contract as `patient360.pdp.rules`.
//! Callers in FastAPI stay on the Python function.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use std::collections::HashSet;

const POLICY_ID: &str = "patient360.pdp.v1";

fn set(items: &[&'static str]) -> HashSet<&'static str> {
    items.iter().copied().collect()
}

fn care_roles() -> HashSet<&'static str> {
    set(&["attending", "care_team", "consultant", "dietary_staff"])
}

fn self_roles() -> HashSet<&'static str> {
    set(&["patient", "caregiver"])
}

fn notes_roles() -> HashSet<&'static str> {
    set(&["attending", "care_team", "consultant", "caregiver", "patient"])
}

fn imaging_roles() -> HashSet<&'static str> {
    set(&["attending", "care_team", "consultant", "caregiver", "patient"])
}

fn pixel_roles() -> HashSet<&'static str> {
    set(&["attending", "consultant", "patient"])
}

fn break_glass_roles() -> HashSet<&'static str> {
    set(&["attending", "care_team", "consultant"])
}

fn identity_roles() -> HashSet<&'static str> {
    set(&["attending", "care_team", "consultant", "caregiver"])
}

fn role_datasets(role: &str) -> Option<HashSet<&'static str>> {
    let all = set(&["labs", "conditions", "meds", "encounters", "allergies", "diet"]);
    match role {
        "attending" | "care_team" | "caregiver" | "patient" => Some(all),
        "consultant" => Some(set(&["labs", "conditions", "meds", "encounters", "allergies"])),
        "dietary_staff" => Some(set(&["allergies", "diet"])),
        "researcher" | "auditor" => Some(HashSet::new()),
        _ => None,
    }
}

fn aggregate_datasets(role: &str) -> Option<HashSet<&'static str>> {
    match role {
        "researcher" => Some(set(&["labs", "conditions", "meds", "encounters", "allergies"])),
        "attending" => Some(set(&["labs", "conditions", "meds", "encounters", "allergies", "diet"])),
        "dietary_staff" => Some(set(&["diet", "allergies"])),
        _ => None,
    }
}

fn aggregate_dims(dataset: &str) -> HashSet<&'static str> {
    match dataset {
        "labs" => set(&["code", "category", "interpretation", "sex", "birth_year"]),
        "conditions" => set(&["code", "clinical_status", "category", "sex", "birth_year"]),
        "meds" => set(&["code", "status", "sex", "birth_year"]),
        "encounters" => set(&["status", "class", "type_code", "dept", "sex", "birth_year"]),
        "allergies" => set(&["code", "category", "sex", "birth_year"]),
        "diet" => set(&["diet_codes", "ward", "sex", "birth_year"]),
        _ => HashSet::new(),
    }
}

fn relation_for(resource_type: &str, dataset: Option<&str>, role: &str) -> Option<&'static str> {
    match resource_type {
        "clinical_rows" => {
            if dataset == Some("diet") || (dataset == Some("allergies") && role == "dietary_staff") {
                Some("can_read_diet")
            } else {
                Some("can_read_clinical")
            }
        }
        "notes" => Some("can_read_notes"),
        "imaging_report" => {
            if role == "care_team" || role == "caregiver" {
                Some("can_read_imaging_metadata")
            } else {
                Some("can_read_imaging_report")
            }
        }
        "imaging_pixels" | "document_bytes" => Some("can_view_pixels"),
        "identity" => Some("can_read_clinical"),
        "consents" => Some("can_delegate"),
        "aggregate" => match role {
            "researcher" => Some("can_query_aggregate"),
            "dietary_staff" => Some("can_read_diet"),
            "attending" => Some("can_read_clinical"),
            _ => None,
        },
        _ => None,
    }
}

struct Decision {
    effect: &'static str,
    reason: &'static str,
    consulted: bool,
}

impl Decision {
    fn deny(reason: &'static str) -> Self {
        Self { effect: "deny", reason, consulted: false }
    }
    fn missing(reason: &'static str, consulted: bool) -> Self {
        Self { effect: "not_found", reason, consulted }
    }
    fn permit(reason: &'static str, consulted: bool) -> Self {
        Self { effect: "permit", reason, consulted }
    }
}

fn dict_str(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<Option<String>> {
    match dict.get_item(key)? {
        Some(value) if !value.is_none() => Ok(Some(value.extract()?)),
        _ => Ok(None),
    }
}

fn dict_bool(dict: &Bound<'_, PyDict>, key: &str, default: bool) -> PyResult<bool> {
    match dict.get_item(key)? {
        Some(value) if !value.is_none() => Ok(value.extract()?),
        _ => Ok(default),
    }
}

fn dict_i64(dict: &Bound<'_, PyDict>, key: &str, default: i64) -> PyResult<i64> {
    match dict.get_item(key)? {
        Some(value) if !value.is_none() => Ok(value.extract()?),
        _ => Ok(default),
    }
}

fn has(set: &HashSet<&'static str>, value: &str) -> bool {
    set.iter().any(|item| *item == value)
}

#[allow(dead_code)]
struct Inputs {
    user_id: String,
    role: String,
    on_duty: bool,
    auth_level: i64,
    self_patient_id: Option<String>,
    resource_type: String,
    patient_key: Option<String>,
    dataset: Option<String>,
    patient_age: Option<i64>,
    now: String,
    channel: String,
    action: String,
    project_id: Option<String>,
    group_by: Vec<String>,
    adolescent_age: i64,
    majority_age: i64,
    target_relation: Option<String>,
    grantee_user_id: Option<String>,
    grantee_role: Option<String>,
    granted_by: Option<String>,
    has_target: bool,
    appointment_created_by: Option<String>,
    appointment_practitioner: Option<String>,
}

fn load_inputs(subject: &Bound<'_, PyDict>, resource: &Bound<'_, PyDict>, context: &Bound<'_, PyDict>) -> PyResult<Inputs> {
    let mut group_by = Vec::new();
    if let Some(value) = context.get_item("group_by")? {
        if !value.is_none() {
            for item in value.downcast::<PyList>()?.iter() {
                group_by.push(item.extract()?);
            }
        }
    }
    let mut target_relation = None;
    let mut grantee_user_id = None;
    let mut grantee_role = None;
    let mut granted_by = None;
    let mut has_target = false;
    if let Some(target) = context.get_item("target")? {
        if !target.is_none() {
            has_target = true;
            let target = target.downcast::<PyDict>()?;
            target_relation = dict_str(target, "relation")?;
            grantee_user_id = dict_str(target, "grantee_user_id")?;
            grantee_role = dict_str(target, "grantee_role")?;
            granted_by = dict_str(target, "granted_by")?;
        }
    }
    Ok(Inputs {
        user_id: dict_str(subject, "user_id")?.unwrap_or_default(),
        role: dict_str(subject, "role")?.unwrap_or_default(),
        on_duty: dict_bool(subject, "on_duty", true)?,
        auth_level: dict_i64(subject, "auth_level", 1)?,
        self_patient_id: dict_str(subject, "self_patient_id")?,
        resource_type: dict_str(resource, "type")?.unwrap_or_default(),
        patient_key: dict_str(resource, "patient_key")?,
        dataset: dict_str(resource, "dataset")?,
        patient_age: match resource.get_item("patient_age")? {
            Some(value) if !value.is_none() => Some(value.extract()?),
            _ => None,
        },
        now: dict_str(context, "now")?.unwrap_or_default(),
        channel: dict_str(context, "channel")?.unwrap_or_else(|| "dashboard".to_string()),
        action: dict_str(context, "action")?.unwrap_or_else(|| "read".to_string()),
        project_id: dict_str(context, "project_id")?,
        group_by,
        adolescent_age: dict_i64(context, "adolescent_age", 14)?,
        majority_age: dict_i64(context, "majority_age", 18)?,
        target_relation,
        grantee_user_id,
        grantee_role,
        granted_by,
        has_target,
        appointment_created_by: dict_str(context, "appointment_created_by")?,
        appointment_practitioner: dict_str(context, "appointment_practitioner")?,
    })
}

fn is_self(inp: &Inputs) -> bool {
    self_roles().contains(inp.role.as_str())
        && inp.self_patient_id.as_deref() == inp.patient_key.as_deref()
        && inp.self_patient_id.is_some()
}

fn holds(check: &Bound<'_, PyAny>, user: &str, relation: &str, object: &str, now: &str) -> PyResult<bool> {
    check.call1((user, relation, object, now))?.extract()
}

fn authority(role: &str) -> Option<&'static str> {
    match role {
        "attending" => Some("can_delegate"),
        "caregiver" => Some("can_consent"),
        _ => None,
    }
}

fn grantable(permission: &str) -> HashSet<&'static str> {
    match permission {
        "can_delegate" => set(&["care_team", "consultant"]),
        _ => set(&["caregiver", "caregiver_notes", "blocked"]),
    }
}

fn grantee_ok(relation: &str, role: &str) -> bool {
    match relation {
        "caregiver" | "caregiver_notes" => role == "caregiver",
        "care_team" => role == "care_team",
        "consultant" => role == "consultant",
        "blocked" => role_datasets(role).is_some(),
        _ => false,
    }
}

fn evaluate_inner(py: Python<'_>, inp: &Inputs, check: &Bound<'_, PyAny>, list_objects: Option<&Bound<'_, PyAny>>) -> PyResult<Decision> {
    if inp.channel == "agent" && inp.action != "read" {
        return Ok(Decision::deny("agent_write_forbidden"));
    }
    if care_roles().contains(inp.role.as_str()) && !inp.on_duty {
        return Ok(Decision::deny("off_duty_step_up_required"));
    }
    if inp.action == "read" && inp.resource_type == "aggregate" {
        return evaluate_aggregate(py, inp, check, list_objects);
    }
    if inp.patient_key.is_none() {
        return Ok(Decision::missing("invalid_resource", false));
    }
    match inp.action.as_str() {
        "read" => evaluate_read(inp, check),
        "consent_grant" | "consent_revoke" => evaluate_consent(inp, check),
        "break_glass" => Ok(evaluate_break_glass(inp)),
        "schedule" | "cancel" => evaluate_schedule(inp, check),
        _ => Ok(Decision::deny("action_not_supported")),
    }
}

fn evaluate_read(inp: &Inputs, check: &Bound<'_, PyAny>) -> PyResult<Decision> {
    if inp.resource_type == "identity" {
        return evaluate_identity(inp, check);
    }
    if inp.resource_type == "consents" {
        return evaluate_consents_list(inp, check);
    }
    if matches!(inp.resource_type.as_str(), "notes" | "imaging_report" | "imaging_pixels" | "document_bytes") {
        return evaluate_gated(inp, check);
    }
    if inp.resource_type != "clinical_rows" {
        return Ok(Decision::missing("resource_type_not_served", false));
    }
    let Some(dataset) = inp.dataset.as_deref() else {
        return Ok(Decision::missing("invalid_resource", false));
    };
    if inp.role == "patient" && !is_self(inp) {
        return Ok(Decision::missing("self_mismatch", false));
    }
    let allowed = role_datasets(&inp.role).unwrap_or_default();
    if !has(&allowed, dataset) {
        let reason = if inp.role == "researcher" { "aggregate_only" } else { "dataset_not_allowed" };
        return Ok(Decision::missing(reason, false));
    }
    if is_self(inp) {
        return Ok(Decision::permit("self_match", false));
    }
    let Some(relation) = relation_for("clinical_rows", Some(dataset), &inp.role) else {
        return Ok(Decision::missing("no_relation_for_resource", false));
    };
    let user = format!("user:{}", inp.user_id);
    let object = format!("patient:{}", inp.patient_key.as_deref().unwrap_or_default());
    if !holds(check, &user, relation, &object, &inp.now)? {
        return Ok(Decision::missing("relationship_missing_or_expired", true));
    }
    Ok(Decision::permit("relationship", true))
}

fn evaluate_gated(inp: &Inputs, check: &Bound<'_, PyAny>) -> PyResult<Decision> {
    if inp.resource_type == "notes" && !notes_roles().contains(inp.role.as_str()) {
        return Ok(Decision::missing("notes_not_allowed", false));
    }
    if inp.resource_type == "imaging_report" && !imaging_roles().contains(inp.role.as_str()) {
        return Ok(Decision::missing("imaging_not_allowed", false));
    }
    if matches!(inp.resource_type.as_str(), "imaging_pixels" | "document_bytes") && !pixel_roles().contains(inp.role.as_str()) {
        return Ok(Decision::missing("pixels_not_allowed", false));
    }
    if inp.role == "patient" && !is_self(inp) {
        return Ok(Decision::missing("self_mismatch", false));
    }
    if is_self(inp) {
        return Ok(Decision::permit("self_match", false));
    }
    let Some(relation) = relation_for(&inp.resource_type, inp.dataset.as_deref(), &inp.role) else {
        return Ok(Decision::missing("no_relation_for_resource", false));
    };
    let user = format!("user:{}", inp.user_id);
    let object = format!("patient:{}", inp.patient_key.as_deref().unwrap_or_default());
    if !holds(check, &user, relation, &object, &inp.now)? {
        return Ok(Decision::missing("relationship_missing_or_expired", true));
    }
    Ok(Decision::permit("relationship", true))
}

fn evaluate_identity(inp: &Inputs, check: &Bound<'_, PyAny>) -> PyResult<Decision> {
    if inp.channel == "agent" {
        return Ok(Decision::deny("identity_agent_forbidden"));
    }
    if inp.role == "patient" {
        return Ok(if is_self(inp) { Decision::permit("self_match", false) } else { Decision::missing("self_mismatch", false) });
    }
    if is_self(inp) {
        return Ok(Decision::permit("self_match", false));
    }
    if !identity_roles().contains(inp.role.as_str()) {
        return Ok(Decision::missing("identity_not_allowed", false));
    }
    let relation = "can_read_clinical";
    let user = format!("user:{}", inp.user_id);
    let object = format!("patient:{}", inp.patient_key.as_deref().unwrap_or_default());
    if !holds(check, &user, relation, &object, &inp.now)? {
        return Ok(Decision::missing("relationship_missing_or_expired", true));
    }
    Ok(Decision::permit("relationship", true))
}

fn evaluate_consents_list(inp: &Inputs, check: &Bound<'_, PyAny>) -> PyResult<Decision> {
    if inp.role == "patient" {
        return Ok(if is_self(inp) { Decision::permit("self_match", false) } else { Decision::missing("self_mismatch", false) });
    }
    if is_self(inp) {
        return Ok(Decision::permit("self_match", false));
    }
    let Some(permission) = authority(&inp.role) else {
        return Ok(Decision::missing("delegate_authority_missing", false));
    };
    let user = format!("user:{}", inp.user_id);
    let object = format!("patient:{}", inp.patient_key.as_deref().unwrap_or_default());
    if !holds(check, &user, permission, &object, &inp.now)? {
        return Ok(Decision::missing("delegate_authority_missing", true));
    }
    let reason = if permission == "can_delegate" { "relationship" } else { "guardian" };
    Ok(Decision::permit(reason, true))
}

fn evaluate_consent(inp: &Inputs, check: &Bound<'_, PyAny>) -> PyResult<Decision> {
    if !inp.has_target {
        return Ok(Decision::missing("invalid_resource", false));
    }
    let relation = inp.target_relation.as_deref().unwrap_or("");
    if inp.role == "patient" && !is_self(inp) {
        return Ok(Decision::missing("self_mismatch", false));
    }
    let (grantable_set, basis, consulted) = if is_self(inp) {
        (grantable("can_consent"), "self_match", false)
    } else {
        let Some(permission) = authority(&inp.role) else {
            return Ok(Decision::missing("delegate_authority_missing", false));
        };
        let user = format!("user:{}", inp.user_id);
        let object = format!("patient:{}", inp.patient_key.as_deref().unwrap_or_default());
        if !holds(check, &user, permission, &object, &inp.now)? {
            return Ok(Decision::missing("delegate_authority_missing", true));
        }
        let basis = if permission == "can_delegate" { "relationship" } else { "guardian" };
        (grantable(permission), basis, true)
    };
    if !has(&grantable_set, relation) {
        return Ok(Decision { effect: "deny", reason: "relation_not_grantable", consulted });
    }
    if inp.action == "consent_grant" {
        if inp.grantee_user_id.is_none() || inp.grantee_user_id.as_deref() == Some(inp.user_id.as_str()) {
            return Ok(Decision { effect: "deny", reason: "grantee_invalid", consulted });
        }
        let Some(role) = inp.grantee_role.as_deref() else {
            return Ok(Decision { effect: "deny", reason: "grantee_unknown", consulted });
        };
        if !grantee_ok(relation, role) {
            return Ok(Decision { effect: "deny", reason: "grantee_role_mismatch", consulted });
        }
    } else if basis == "relationship" && inp.granted_by.as_deref() != Some(inp.user_id.as_str()) {
        return Ok(Decision { effect: "deny", reason: "not_granted_by_subject", consulted });
    }
    Ok(Decision::permit(basis, consulted))
}

fn evaluate_break_glass(inp: &Inputs) -> Decision {
    if !break_glass_roles().contains(inp.role.as_str()) {
        return Decision::deny("break_glass_role_not_allowed");
    }
    if inp.auth_level < 2 {
        return Decision::deny("step_up_required");
    }
    Decision::permit("break_glass", false)
}

fn evaluate_aggregate(
    py: Python<'_>,
    inp: &Inputs,
    check: &Bound<'_, PyAny>,
    list_objects: Option<&Bound<'_, PyAny>>,
) -> PyResult<Decision> {
    let Some(dataset) = inp.dataset.as_deref() else {
        return Ok(Decision::missing("invalid_resource", false));
    };
    let Some(allowed) = aggregate_datasets(&inp.role) else {
        return Ok(Decision::missing("aggregate_role_not_allowed", false));
    };
    if !has(&allowed, dataset) {
        return Ok(Decision::missing("dataset_not_allowed", false));
    }
    let dims = aggregate_dims(dataset);
    if inp.group_by.iter().any(|dim| !has(&dims, dim)) {
        return Ok(Decision::missing("dim_not_allowed", false));
    }
    if inp.role == "researcher" {
        let Some(project) = inp.project_id.as_deref() else {
            return Ok(Decision::missing("aggregate_project_missing", false));
        };
        let user = format!("user:{}", inp.user_id);
        let object = format!("project:{project}");
        if !holds(check, &user, "can_query_aggregate", &object, &inp.now)? {
            return Ok(Decision::missing("relationship_missing_or_expired", true));
        }
        return Ok(Decision::permit("aggregate_project", true));
    }
    let Some(list_objects) = list_objects else {
        return Ok(Decision::missing("aggregate_scope_unavailable", false));
    };
    let relation = if inp.role == "dietary_staff" { "can_read_diet" } else { "can_read_clinical" };
    let user = format!("user:{}", inp.user_id);
    let listed: Vec<String> = list_objects.call1((user, relation, "patient", &inp.now))?.extract()?;
    let _ = py;
    if !listed.iter().any(|object| object.starts_with("patient:")) {
        return Ok(Decision::missing("relationship_missing_or_expired", true));
    }
    Ok(Decision::permit("aggregate_own", true))
}

fn evaluate_schedule(inp: &Inputs, check: &Bound<'_, PyAny>) -> PyResult<Decision> {
    if inp.action == "cancel" {
        if is_self(inp) {
            return Ok(Decision::permit("self_match", false));
        }
        if Some(inp.user_id.as_str()) == inp.appointment_created_by.as_deref()
            || Some(inp.user_id.as_str()) == inp.appointment_practitioner.as_deref()
        {
            return Ok(Decision::permit("appointment_party", false));
        }
        return Ok(Decision::missing("cancel_not_allowed", false));
    }
    if inp.role == "patient" {
        return Ok(if is_self(inp) { Decision::permit("self_match", false) } else { Decision::missing("self_mismatch", false) });
    }
    if is_self(inp) {
        return Ok(Decision::permit("self_match", false));
    }
    let user = format!("user:{}", inp.user_id);
    let object = format!("patient:{}", inp.patient_key.as_deref().unwrap_or_default());
    if !holds(check, &user, "can_schedule", &object, &inp.now)? {
        return Ok(Decision::missing("relationship_missing_or_expired", true));
    }
    Ok(Decision::permit("relationship", true))
}

#[pyfunction]
#[pyo3(signature = (subject, resource, context, check, list_objects=None))]
fn evaluate<'py>(
    py: Python<'py>,
    subject: Bound<'py, PyDict>,
    resource: Bound<'py, PyDict>,
    context: Bound<'py, PyDict>,
    check: Bound<'py, PyAny>,
    list_objects: Option<Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyDict>> {
    let inp = load_inputs(&subject, &resource, &context)?;
    let decision = evaluate_inner(py, &inp, &check, list_objects.as_ref())?;
    let out = PyDict::new(py);
    out.set_item("effect", decision.effect)?;
    out.set_item("reason_code", decision.reason)?;
    out.set_item("fga_consulted", decision.consulted)?;
    out.set_item("policy_id", POLICY_ID)?;
    Ok(out)
}

#[pymodule]
fn pdp_rs(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(evaluate, module)?)?;
    Ok(())
}
