//! Every matrix in data/cases/*.json against sysml-toolkit's semantic model API,
//! `ResolvedModel`: owned properties through `element_properties`, derived
//! properties through `derived(element, "<spec name>")` (DISCUSSIONS.md, Step 3).
use serde_json::{json, Value};
use std::fs;
use std::path::PathBuf;
use sysmlv2_parser::json::{metaclass_conforms, Derived, DerivedValue, ElementRef, Reference, ResolvedModel};
use sysmlv2_parser::model::Model;

enum Outcome {
    Value(Value),
    Unsupported(String),
}
use Outcome::*;

fn root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}

struct Api {
    rm: ResolvedModel,
}

impl Api {
    fn qn(&mut self, e: ElementRef) -> Option<String> {
        self.rm.element_qualified_name(e)
    }
    fn find(&mut self, qn: &str) -> Option<ElementRef> {
        self.rm.resolve_qualified(qn)
    }
    /// A property by spec name: owned if the element carries it, else derived.
    fn prop(&mut self, e: ElementRef, name: &str) -> Result<DerivedOrOwned, String> {
        if let Some(v) = self.rm.element_properties(e).get(name) {
            return Ok(DerivedOrOwned::Owned(v.clone()));
        }
        match self.rm.derived(e, name) {
            Derived::Value(v) => Ok(DerivedOrOwned::Derived(v)),
            Derived::NotComputed => Err(format!("{name} is not computed by the toolkit")),
            Derived::NotDeclared => Ok(DerivedOrOwned::Owned(Value::Null)),
        }
    }
    fn elements(&mut self, e: ElementRef, name: &str) -> Result<Vec<ElementRef>, String> {
        Ok(match self.prop(e, name)? {
            DerivedOrOwned::Derived(v) => v.elements().into_iter().chain(v.element()).collect(),
            // owned properties spell element references as {"@id": ...}
            DerivedOrOwned::Owned(v) => {
                let refs: Vec<Value> = match v {
                    Value::Array(a) => a,
                    Value::Object(_) => vec![v],
                    _ => vec![],
                };
                refs.iter().filter_map(|r| r["@id"].as_str()).filter_map(|id| self.rm.element_by_id(id)).collect()
            }
        })
    }
    fn element(&mut self, e: ElementRef, name: &str) -> Result<Option<ElementRef>, String> {
        Ok(self.elements(e, name)?.into_iter().next())
    }
    fn scalar(&mut self, e: ElementRef, name: &str) -> Result<Value, String> {
        Ok(match self.prop(e, name)? {
            DerivedOrOwned::Owned(v) => v,
            DerivedOrOwned::Derived(DerivedValue::Str(s)) => json!(s),
            DerivedOrOwned::Derived(DerivedValue::Bool(b)) => json!(b),
            DerivedOrOwned::Derived(DerivedValue::Null) => Value::Null,
            DerivedOrOwned::Derived(other) => json!(format!("{other:?}")),
        })
    }
    /// Everything visible in a type: the union of the spec's `feature`, `ownedFeature`,
    /// `inheritedFeature` and `member`, and the members of its inherited memberships.
    fn visible_features(&mut self, t: ElementRef) -> Result<Vec<ElementRef>, String> {
        let mut out = vec![];
        for p in ["feature", "ownedFeature", "inheritedFeature", "member"] {
            for f in self.elements(t, p)? {
                if !out.contains(&f) {
                    out.push(f);
                }
            }
        }
        // the members of inherited memberships (Namespace::member includes them), such as
        // a body annotation `@M;` of a general type
        for ms in self.elements(t, "inheritedMembership")? {
            for f in self.elements(ms, "memberElement")? {
                if !out.contains(&f) {
                    out.push(f);
                }
            }
        }
        Ok(out)
    }
    /// A referenced feature in chain form: its chainingFeatures' qualified names,
    /// or a one-element list when it is not a chain.
    fn chain_form(&mut self, f: ElementRef) -> Result<Value, String> {
        let chain = self.elements(f, "chainingFeature")?;
        let parts = if chain.is_empty() { vec![f] } else { chain };
        Ok(json!(parts.into_iter().map(|p| self.qn(p)).collect::<Vec<_>>()))
    }
    /// The value expression of the feature's owned FeatureValue membership.
    fn value_expr(&mut self, e: ElementRef) -> Result<Option<ElementRef>, String> {
        let fv = self.elements(e, "ownedMembership")?.into_iter().find(|m| self.metaclass(*m) == "FeatureValue");
        match fv {
            Some(fv) => self.element(fv, "value"),
            None => Ok(None),
        }
    }
    /// Referenced features of an expression, left to right, each in chain form.
    fn references(&mut self, x: ElementRef) -> Result<Vec<Value>, String> {
        let mc = self.metaclass(x);
        if mc == "FeatureReferenceExpression" {
            return Ok(match self.element(x, "referent")? {
                Some(f) => vec![self.chain_form(f)?],
                None => vec![],
            });
        }
        if mc == "FeatureChainExpression" {
            let args = self.elements(x, "argument")?;
            let mut chain: Vec<Value> = match args.first() {
                Some(a) => match self.references(*a)?.pop() {
                    Some(Value::Array(c)) => c,
                    _ => vec![],
                },
                None => vec![],
            };
            if let Some(t) = self.element(x, "targetFeature")? {
                if let Value::Array(tc) = self.chain_form(t)? {
                    chain.extend(tc);
                }
            }
            return Ok(vec![Value::Array(chain)]);
        }
        let mut out = vec![];
        for a in self.elements(x, "argument")? {
            out.extend(self.references(a)?);
        }
        Ok(out)
    }
    /// MetadataUsages whose annotatedElement includes `e`, wherever they are owned.
    fn annotations(&mut self, e: ElementRef) -> Result<Vec<ElementRef>, String> {
        let candidates: Vec<ElementRef> = self.rm.user_elements().filter(|x| self.rm.element_type(*x) == "MetadataUsage").collect();
        let mut out = vec![];
        for mu in candidates {
            if self.elements(mu, "annotatedElement")?.contains(&e) {
                out.push(mu);
            }
        }
        Ok(out)
    }
    /// A comment's body, trimmed.
    fn body(&mut self, c: ElementRef) -> Result<String, String> {
        Ok(self.scalar(c, "body")?.as_str().unwrap_or("").trim().to_string())
    }
    fn metaclass(&self, e: ElementRef) -> &'static str {
        self.rm.element_type(e)
    }
    /// The value of a literal expression, as JSON ("*" for LiteralInfinity).
    fn literal(&mut self, expr: ElementRef) -> Result<Value, String> {
        if self.metaclass(expr) == "LiteralInfinity" {
            return Ok(json!("*"));
        }
        self.scalar(expr, "value")
    }
}

enum DerivedOrOwned {
    Owned(Value),
    Derived(DerivedValue),
}

/// Qualified names compared without quoting (`CmdPort::'~CmdPort'` vs `CmdPort::~CmdPort`).
fn norm(qn: &str) -> String {
    qn.replace('\'', "")
}

/// The case's `through`: absent, one qualified name, or a path.
fn through_path(c: &Value) -> Vec<String> {
    match &c["through"] {
        Value::String(s) => vec![s.clone()],
        Value::Array(a) => a.iter().map(|v| v.as_str().unwrap().to_string()).collect(),
        _ => vec![],
    }
}

fn bound_text(v: &Value) -> String {
    match v {
        Value::String(s) => s.clone(),
        Value::Number(n) => n.to_string(),
        other => other.to_string(),
    }
}

fn check(api: &mut Api, c: &Value) -> Result<Outcome, String> {
    let check = c["check"].as_str().unwrap();
    let element = c["element"].as_str().unwrap();
    let path = through_path(c);
    let through = path.first().map(String::as_str);

    if check == "evaluatedValue" || check == "evaluatedUnit" {
        // E10: the feature's value from the evaluation API: evaluate (in its part def) or
        // evaluate_qualified("<usage>::<feature>") (the usage path sets the context)
        let result = match c["subject"].as_str() {
            Some(subject) => {
                let name = element.rsplit("::").next().unwrap();
                api.rm.evaluate_qualified(&format!("{subject}::{name}"))
            }
            None => {
                let e = api.find(element).ok_or("no element")?;
                api.rm.evaluate(e)
            }
        };
        let v = match result {
            Ok(v) => v,
            Err(err) => return Ok(Value(json!(format!("<evaluation failed: {err:?}>")))),
        };
        // read through the toolkit's own rendering: "1500.0 [kg]", "6.5", "true", "\"pump\""
        let text = api.rm.render_value(&v);
        let (magnitude, unit) = match (text.find(" ["), text.ends_with(']')) {
            (Some(i), true) => (text[..i].to_string(), Some(text[i + 2..text.len() - 1].to_string())),
            _ => (text.clone(), None),
        };
        if check == "evaluatedUnit" {
            return Ok(Value(json!(unit)));
        }
        let parsed = if let Ok(n) = magnitude.parse::<f64>() {
            json!(n)
        } else if magnitude == "true" || magnitude == "false" {
            json!(magnitude == "true")
        } else {
            json!(magnitude.trim_matches('"'))
        };
        return Ok(Value(parsed));
    }
    if check == "resolve" {
        // KerML Namespace::resolve of the rest of the path, invoked on the matrix's root package
        let (first, rest) = element.split_once("::").ok_or("path needs a package")?;
        let package = api.find(first).ok_or("no root package")?;
        let r = api.rm.invoke_operation(package, "Root-Namespaces-Namespace-resolve_String",
            &[DerivedValue::Str(rest.to_string())]).map_err(|err| format!("resolve: {err:?}"))?;
        return Ok(Value(match r.value.element() {
            Some(membership) => {
                // an OwningMembership redefines memberElement as ownedMemberElement
                let mut target = api.element(membership, "memberElement")?;
                if target.is_none() {
                    target = api.element(membership, "ownedMemberElement")?;
                }
                match target {
                    Some(t) => json!(api.qn(t)),
                    None => Value::Null,
                }
            }
            None => Value::Null,
        }));
    }
    if check == "unnamedPartCount" {
        let scope = api.find(through.unwrap_or(element)).ok_or("no scope element")?;
        let members = if through.is_some() { api.visible_features(scope)? } else { api.elements(scope, "ownedMember")? };
        let mut n = 0;
        for m in members {
            let unnamed = api.scalar(m, "name")?.is_null();
            let owner = api.element(m, "owningNamespace")?;
            let owner_qn = owner.and_then(|o| api.qn(o));
            if api.metaclass(m) == "PartUsage" && unnamed && owner_qn.as_deref() == Some(element) {
                n += 1;
            }
        }
        return Ok(Value(json!(n)));
    }

    // the element, read through each step of the path as a member visible in the previous one
    let mut owner = None;
    let unnamed = &c["unnamed"];
    let e = if unnamed.is_object() {
        // the index-th unnamed member of the metaclass declared in `element`
        let (scope, members) = if path.is_empty() {
            let s = api.find(element).ok_or("no element")?;
            (s, api.elements(s, "ownedMember")?)
        } else {
            let mut cur = api.find(&path[0]).ok_or("no element")?;
            for step in &path[1..] {
                let found = api.visible_features(cur)?.into_iter()
                    .find(|f| api.qn(*f).map(|q| norm(&q)) == Some(norm(step)));
                cur = match found {
                    Some(f) => f,
                    None => return Ok(Value(json!(format!("<{step} not visible>")))),
                };
            }
            (cur, api.visible_features(cur)?)
        };
        let metaclass = unnamed["metaclass"].as_str().unwrap();
        let mut found = vec![];
        for m in members {
            let owner_qn = match api.element(m, "owningNamespace")? {
                Some(o) => api.qn(o),
                None => None,
            };
            if api.scalar(m, "name")?.is_null() && api.metaclass(m).contains(metaclass)
                && owner_qn.as_deref() == Some(element) {
                found.push(m);
            }
        }
        owner = Some(scope);
        match found.get(unnamed["index"].as_u64().unwrap() as usize) {
            Some(e) => *e,
            None => return Ok(Value(json!(format!("<unnamed {metaclass} of {element} not listed>")))),
        }
    } else if path.is_empty() {
        match api.find(element) {
            Some(e) => e,
            None => return Ok(Unsupported(format!("no element {element}"))),
        }
    } else {
        let mut cur = api.find(&path[0]).ok_or(format!("no element {}", path[0]))?;
        for step in path[1..].iter().map(String::as_str).chain([element]) {
            let found = api.visible_features(cur)?.into_iter()
                .find(|f| api.qn(*f).map(|q| norm(&q)) == Some(norm(step)));
            match found {
                Some(f) => {
                    owner = Some(cur);
                    cur = f;
                }
                None => {
                    let cur_qn = api.qn(cur).unwrap_or_default();
                    return Ok(Value(json!(format!("<{step} not visible through {cur_qn}>"))));
                }
            }
        }
        cur
    };
    Ok(Value(match check {
        "name" => api.scalar(e, "name")?,
        "type" => match api.element(e, "type")? {
            Some(t) => json!(api.qn(t)),
            None => Value::Null,
        },
        "isComposite" => api.scalar(e, "isComposite")?,
        "kind" => json!(api.metaclass(e)),
        "documentation" => {
            let mut out = vec![];
            for d in api.elements(e, "documentation")? {
                out.push(api.body(d)?);
            }
            out.sort();
            json!(out)
        }
        "comments" => {
            // Comments (not Documentation) whose annotatedElement includes e, wherever owned
            let candidates: Vec<ElementRef> = api.rm.user_elements().filter(|x| api.rm.element_type(*x) == "Comment").collect();
            let mut out = vec![];
            for c in candidates {
                if api.elements(c, "annotatedElement")?.contains(&e) {
                    out.push(api.body(c)?);
                }
            }
            out.sort();
            json!(out)
        }
        "textualRepresentation" => {
            let mut out = vec![];
            for r in api.elements(e, "textualRepresentation")? {
                let lang = api.scalar(r, "language")?;
                out.push(json!([lang, api.body(r)?]));
            }
            out.sort_by_key(|v| v.to_string());
            json!(out)
        }
        "entryKind" | "doKind" | "exitKind" | "guardKind" | "effectKind" => {
            let prop = match check {
                "entryKind" => "entryAction", "doKind" => "doAction", "exitKind" => "exitAction",
                "guardKind" => "guardExpression", _ => "effectAction",
            };
            match api.element(e, prop)? {
                Some(a) => json!(api.metaclass(a)),
                None => Value::Null,
            }
        }
        "substates" => {
            let mut out = vec![];
            for f in api.elements(e, "ownedFeature")? {
                if api.metaclass(f) == "StateUsage" {
                    out.push(api.scalar(f, "name")?.as_str().unwrap_or("").to_string());
                }
            }
            out.sort();
            json!(out)
        }
        "isParallel" => api.scalar(e, "isParallel")?,
        "source" | "target" => match api.element(e, check)? {
            Some(s) => json!(api.qn(s)),
            None => Value::Null,
        },
        "triggerPayload" => {
            let mut v = Value::Null;
            if let Some(acc) = api.element(e, "triggerAction")? {
                if let Some(p) = api.element(acc, "payloadParameter")? {
                    if let Some(t) = api.element(p, "type")? {
                        v = json!(api.qn(t));
                    }
                }
            }
            v
        }
        "payloadTypes" => {
            let mut out: Vec<_> = api.elements(e, "payloadType")?.into_iter().map(|t| api.qn(t)).collect();
            out.sort();
            json!(out)
        }
        "sourceOutput" | "targetInput" => {
            let prop = if check == "sourceOutput" { "sourceOutputFeature" } else { "targetInputFeature" };
            let mut target = Value::Null;
            if let Some(f) = api.element(e, prop)? {
                // the flow feature redefines the participant's feature it names
                for r in api.elements(f, "ownedRedefinition")? {
                    if let Some(rf) = api.element(r, "redefinedFeature")? {
                        target = json!(api.qn(rf));
                    }
                }
            }
            target
        }
        "referenceTarget" => {
            if c["via"] == "type" {
                match api.element(e, "type")? {
                    Some(t) => json!(api.qn(t)),
                    None => Value::Null,
                }
            } else {
                let mut target = Value::Null;
                for r in api.elements(e, "ownedSubsetting")? {
                    if api.rm.element_properties(r).get("isImplied") == Some(&json!(true)) {
                        continue;
                    }
                    if let Some(f) = api.element(r, "subsettedFeature")? {
                        target = json!(api.qn(f));
                        break;
                    }
                }
                target
            }
        }
        "specializations" | "subsettedFeatures" => {
            let mut out = vec![];
            let prop = if check == "specializations" { "ownedSpecialization" } else { "ownedSubsetting" };
            for r in api.elements(e, prop)? {
                if api.rm.element_properties(r).get("isImplied") == Some(&json!(true)) {
                    continue;
                }
                // each kind of Specialization redefines `general` (and a Subsetting's
                // `subsettedFeature`) under its own name, which is what the toolkit stores
                let prop = match api.metaclass(r) {
                    "FeatureTyping" | "ConjugatedPortTyping" => "type",
                    "Subsetting" => "subsettedFeature",
                    "Redefinition" => "redefinedFeature",
                    "ReferenceSubsetting" => "referencedFeature",
                    "Subclassification" => "superclassifier",
                    _ => "general",
                };
                let general = api.element(r, prop)?.and_then(|g| api.qn(g));
                if check == "specializations" {
                    out.push(json!([api.metaclass(r), general]));
                } else if general.is_some() {
                    out.push(json!(general));
                }
            }
            out.sort_by_key(|v| v.to_string());
            json!(out)
        }
        "types" => {
            let mut out: Vec<_> = api.elements(e, "type")?.into_iter().map(|t| api.qn(t)).collect();
            out.sort();
            json!(out)
        }
        "owner" => match api.element(e, "owningNamespace")? {
            Some(o) => json!(api.qn(o)),
            None => Value::Null,
        },
        "idRoundTrip" => {
            let id = api.rm.element_id(e).to_string();
            json!(api.rm.element_by_id(&id) == Some(e))
        }
        "directGenerals" => {
            let mut out = vec![];
            for r in api.elements(e, "ownedSubclassification")? {
                if api.rm.element_properties(r).get("isImplied") == Some(&json!(true)) {
                    continue;
                }
                if let Some(g) = api.element(r, "superclassifier")? {
                    out.push(api.qn(g));
                }
            }
            out.sort();
            json!(out)
        }
        "allSupertypes" => {
            let r = api.rm.invoke_operation(e, "Core-Types-Type-allSupertypes_", &[])
                .map_err(|err| format!("allSupertypes: {err:?}"))?;
            let mut out: Vec<_> = r.value.elements().into_iter().map(|t| api.qn(t)).collect();
            out.sort();
            json!(out)
        }
        "ownedFeatureNames" | "inheritedFeatureNames" => {
            let mut out = vec![];
            for f in api.elements(e, if check == "ownedFeatureNames" { "ownedFeature" } else { "inheritedFeature" })? {
                out.push(api.scalar(f, "name")?.as_str().unwrap_or("").to_string());
            }
            out.sort();
            json!(out)
        }
        "redefinitions" => {
            let mut out = vec![];
            for f in api.elements(e, "ownedFeature")? {
                for r in api.elements(f, "ownedRedefinition")? {
                    if let Some(rf) = api.element(r, "redefinedFeature")? {
                        out.push(json!([api.qn(f), api.qn(rf)]));
                    }
                }
            }
            out.sort_by_key(|v| v.to_string());
            json!(out)
        }
        "shortName" => api.scalar(e, "shortName")?,
        "isAbstract" => api.scalar(e, "isAbstract")?,
        "isVariation" => api.scalar(e, "isVariation")?,
        "parameters" => {
            let mut out = vec![];
            for f in api.elements(e, "directedFeature")? {
                let r = api.rm.invoke_operation(e, "Core-Types-Type-directionOf_Feature",
                    &[DerivedValue::Reference(Reference::Element(f))]).map_err(|err| format!("directionOf: {err:?}"))?;
                let dir = match r.value {
                    DerivedValue::Literal(s) | DerivedValue::Str(s) => json!(s),
                    _ => Value::Null,
                };
                out.push(json!([dir, api.scalar(f, "name")?.as_str().unwrap_or("")]));
            }
            out.sort_by_key(|v| v.to_string());
            json!(out)
        }
        "result" | "subject" => match api.element(e, if check == "result" { "result" } else { "subjectParameter" })? {
            Some(p) => api.scalar(p, "name")?,
            None => Value::Null,
        },
        "isIndividual" => api.scalar(e, "isIndividual")?,
        "variants" => {
            let mut out = vec![];
            for v in api.elements(e, "variant")? {
                out.push(api.scalar(v, "name")?.as_str().unwrap_or("").to_string());
            }
            out.sort();
            json!(out)
        }
        "metadataDefs" => {
            let mut defs = vec![];
            for mu in api.annotations(e)? {
                if let Some(d) = api.element(mu, "metadataDefinition")? {
                    defs.push(api.qn(d));
                }
            }
            defs.sort();
            json!(defs)
        }
        "metadataValue" | "annotatedElement" => match api.annotations(e)?.first().copied() {
            None => json!(format!("<no annotation of {element} found>")),
            Some(mu) if check == "annotatedElement" => {
                let mut out = vec![];
                for a in api.elements(mu, "annotatedElement")? {
                    out.push(api.qn(a));
                }
                json!(out)
            }
            Some(mu) => {
                let mut v = Value::Null;
                for f in api.elements(mu, "ownedFeature")? {
                    if api.scalar(f, "name")? == json!("severity") {
                        if let Some(x) = api.value_expr(f)? {
                            v = api.literal(x)?;
                        }
                    }
                }
                v
            }
        },
        "payloadArgument" | "senderArgument" | "receiverArgument" => match api.element(e, check)? {
            Some(x) => json!(api.references(x)?),
            None => Value::Null,
        },
        "assignedFeature" => match api.element(e, "referent")? {
            Some(f) => api.chain_form(f)?,
            None => Value::Null,
        },
        "valueText" => return Ok(Unsupported("no accessor returns an expression's source text".into())),
        "valueKind" | "valueOperator" | "valueReferences" => match api.value_expr(e)? {
            None => Value::Null,
            Some(x) => match check {
                "valueKind" => json!(api.metaclass(x)),
                "valueOperator" if metaclass_conforms(api.metaclass(x), "OperatorExpression") => api.scalar(x, "operator")?,
                "valueOperator" => Value::Null,
                _ => json!(api.references(x)?),
            },
        },
        "endCount" | "endNames" => {
            let is_def = api.metaclass(e).ends_with("Definition");
            let ends = api.elements(e, if is_def { "endFeature" } else { "connectorEnd" })?;
            if check == "endCount" {
                json!(ends.len())
            } else {
                let mut names = vec![];
                for x in ends {
                    names.push(api.scalar(x, "name")?);
                }
                json!(names)
            }
        }
        "endReferences" => {
            let mut out = vec![];
            for end in api.elements(e, "connectorEnd")? {
                let target = match api.element(end, "ownedReferenceSubsetting")? {
                    Some(rs) => api.element(rs, "referencedFeature")?,
                    None => None,
                };
                out.push(match target {
                    Some(f) => api.chain_form(f)?,
                    None => Value::Null,
                });
            }
            json!(out)
        }
        "sourceFeature" => match api.element(e, "sourceFeature")? {
            Some(f) => api.chain_form(f)?,
            None => Value::Null,
        },
        "targetFeature" | "relatedFeature" => {
            let mut out = vec![];
            for f in api.elements(e, check)? {
                out.push(api.chain_form(f)?);
            }
            json!(out)
        }
        "typeIsConjugated" => match api.element(e, "type")? {
            Some(t) => json!(api.metaclass(t) == "ConjugatedPortDefinition"),
            None => Value::Null,
        },
        "direction" => {
            let Some(receiver) = owner else {
                return Ok(Value(api.scalar(e, "direction")?));
            };
            let r = api.rm.invoke_operation(receiver, "Core-Types-Type-directionOf_Feature",
                &[DerivedValue::Reference(Reference::Element(e))]).map_err(|err| format!("directionOf: {err:?}"))?;
            match r.value {
                DerivedValue::Null => Value::Null,
                DerivedValue::Literal(s) | DerivedValue::Str(s) => json!(s),
                other => json!(format!("{other:?}")),
            }
        }
        "isReference" => api.scalar(e, "isReference")?,
        "multiplicity" => match api.element(e, "multiplicity")? {
            None => Value::Null,
            Some(m) => {
                let upper = match api.element(m, "upperBound")? {
                    Some(u) => api.literal(u)?,
                    None => Value::Null,
                };
                let lower = match api.element(m, "lowerBound")? {
                    Some(l) => api.literal(l)?,
                    None if upper == json!("*") => json!(0),
                    None => upper.clone(),
                };
                json!(format!("{}..{}", bound_text(&lower), bound_text(&upper)))
            }
        },
        // a value is the feature's owned membership of metaclass FeatureValue
        "value" | "isDefault" => match api.elements(e, "ownedMembership")?.into_iter().find(|m| api.metaclass(*m) == "FeatureValue") {
            None => Value::Null,
            Some(fv) if check == "isDefault" => api.scalar(fv, "isDefault")?,
            Some(fv) => match api.element(fv, "value")? {
                Some(expr) => api.literal(expr)?,
                None => Value::Null,
            },
        },
        other => return Err(format!("unknown check {other}")),
    }))
}

fn matches(actual: &Value, want: &Value) -> bool {
    match (actual.as_f64(), want.as_f64()) {
        (Some(a), Some(w)) => a == w,
        _ => actual == want,
    }
}

#[test]
fn matrices() {
    let mut files: Vec<_> = fs::read_dir(root().join("../data/cases")).unwrap()
        .map(|e| e.unwrap().path()).filter(|p| p.extension().is_some_and(|x| x == "json")).collect();
    files.sort();
    let specs: Vec<Value> = files.iter()
        .map(|f| serde_json::from_str(&fs::read_to_string(f).unwrap()).unwrap()).collect();

    // One model: the standard library plus every matrix's model (each its own package).
    let mut model = Model::new();
    model.load_library_dir(&root().join("../../sysml-toolkit/spec-refs/SysML-v2-Release/sysml.library"))
        .expect("standard library (initialise the sysml-toolkit submodule spec-refs/SysML-v2-Release)");
    // every matrix's model, and any model a case names for itself
    let mut files: Vec<String> = vec![];
    for s in &specs {
        let own = std::iter::once(s["model"].as_str().unwrap().to_string());
        let per_case = s["cases"].as_array().unwrap().iter().filter_map(|c| c["model"].as_str().map(String::from));
        for f in own.chain(per_case) {
            if !files.contains(&f) {
                files.push(f);
            }
        }
    }
    for file in &files {
        model.add_source(file.as_str(), &fs::read_to_string(root().join("../data").join(file)).unwrap());
    }
    // a model the MDK reports errors for: every case of that matrix is an error
    let mut rejected = std::collections::HashMap::new();
    for i in 0..model.unit_count() {
        if model.is_library_unit(i) {
            continue;
        }
        let unit = &model.units()[i];
        let errors: Vec<String> = unit.diagnostics.iter()
            .filter(|d| matches!(d.severity, sysmlv2_parser::diag::Severity::Error))
            .take(2).map(|d| d.message.clone()).collect();
        if !errors.is_empty() {
            rejected.insert(unit.name.clone(), format!("model rejected: {}", errors.join("; ")));
        }
    }
    let mut api = Api { rm: ResolvedModel::build(&model) };

    let mut rows: Vec<[String; 5]> = vec![];
    let mut failed = vec![];
    for s in &specs {
        let matrix = s["matrix"].as_str().unwrap();
        let model_file = s["model"].as_str().unwrap();
        for c in s["cases"].as_array().unwrap() {
            let id = c["id"].as_str().unwrap();
            let result = match rejected.get(c["model"].as_str().unwrap_or(model_file)) {
                Some(why) => Err(why.clone()),
                None => check(&mut api, c),
            };
            let (outcome, detail) = match result {
                Err(e) => ("error", e),
                Ok(Unsupported(why)) => ("unsupported", why),
                Ok(Value(v)) => {
                    let accepted = c["accept"].as_array().is_some_and(|a| a.iter().any(|w| matches(&v, w)));
                    if matches(&v, &c["expect"]) || accepted {
                        ("pass", String::new())
                    } else {
                        ("fail", format!("{} {}: got {v}, want {}", c["check"].as_str().unwrap(), c["element"].as_str().unwrap(), c["expect"]))
                    }
                }
            };
            println!("{id} {outcome} {detail}");
            if outcome == "fail" || outcome == "error" {
                failed.push(id.to_string());
            }
            rows.push(["sysml-toolkit-rs".into(), matrix.into(), id.into(), outcome.into(), detail]);
        }
    }
    write_csv(&rows);
    assert!(failed.is_empty(), "failed: {failed:?}");
}

fn write_csv(rows: &[[String; 5]]) {
    let dir = std::env::var("RESULTS_DIR").map(PathBuf::from).unwrap_or_else(|_| root().join("../results"));
    fs::create_dir_all(&dir).unwrap();
    let q = |s: &str| format!("\"{}\"", s.replace('"', "\"\"").replace('\n', " "));
    let mut out = String::from("suite,matrix,id,outcome,detail\n");
    for r in rows {
        out.push_str(&r.iter().map(|c| q(c)).collect::<Vec<_>>().join(","));
        out.push('\n');
    }
    fs::write(dir.join("sysml-toolkit-rs.csv"), out).unwrap();
}
