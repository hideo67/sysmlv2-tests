//! Every matrix in data/cases/*.json against the OpenSysML Rust client (client/rust),
//! over the locally built sysml-grpc.
//!
//! Only the Symbol API is used: it is OpenSysML's element API, the counterpart of the
//! Pilot's EMF model and sysml-toolkit's ResolvedModel (DISCUSSIONS.md, Step 5 decision).
//! When the Symbol API has no field for a read, the result is unsupported, and the detail
//! says whether the standard SysML v2 API & Services query API offers the property; the
//! query API is consulted for that note only, never for a value.
//!
//! The Rust client offers the same Symbol methods as the Python client (`Model::get`,
//! `Symbol::children`, `parts`, `attributes`, `attribute_facts`), so each read takes the
//! same route as in the Python suite; a different result is a difference of the client.
use opensysml::{
    Connection, EvalOptions, Instance, Instantiation, Magnitude, Model, ParseOptions, Query,
    Symbol, SymbolOptions, Value as OValue,
};
use serde_json::{json, Value};
use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;

const SUITE: &str = "opensysml-rs";

/// Why a check stops before reaching its last line.
enum Stop {
    /// The API failed or the case could not be run.
    Error(String),
    /// The read is answered early (an element not visible, not listed, not found).
    Answer(Value),
    /// The API offers no way to obtain this information.
    Unsupported(String),
}
use Stop::*;

impl From<opensysml::Error> for Stop {
    fn from(e: opensysml::Error) -> Self {
        Error(e.to_string())
    }
}

type R<T> = Result<T, Stop>;

fn root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}

/// Qualified names compared without quoting: OpenSysML spells `CmdPort::~CmdPort`
/// where the textual notation quotes `CmdPort::'~CmdPort'`.
fn norm(qn: &str) -> String {
    qn.replace('\'', "")
}

fn parent(qn: &str) -> &str {
    qn.rfind("::").map_or("", |i| &qn[..i])
}

fn last(qn: &str) -> &str {
    qn.rfind("::").map_or(qn, |i| &qn[i + 2..])
}

fn answer(text: String) -> Stop {
    Answer(json!(text))
}

/// The Symbol API's name lookup, `Model::get(qualified name)`, as written or unquoted.
fn get(m: &Model, qn: &str) -> R<Option<Symbol>> {
    if let Some(s) = m.get(qn)? {
        return Ok(Some(s));
    }
    Ok(m.get(&norm(qn))?)
}

/// Symbol kinds that are not features (internal/semantic/symbols/symbol.go); every other
/// kind, the usages above all, is a feature.
const NON_FEATURE_KINDS: [&str; 10] = ["documentation", "comment", "textualRepresentation", "alias",
    "dependency", "relationship", "namespace", "package", "kermlType", "metaclass"];

fn is_feature_kind(kind: &str) -> bool {
    !NON_FEATURE_KINDS.contains(&kind) && !kind.ends_with("Def")
}

fn sym(m: &Model, qn: &str) -> R<Symbol> {
    get(m, qn)?.ok_or_else(|| answer(format!("<no symbol {qn}>")))
}

/// Members a Symbol lists: children, parts, attributes (own and inherited), and the
/// members its SymbolInfo enumerates (own and inherited, library-inherited ones
/// included), by unquoted id.
fn visible(m: &Model, s: &Symbol) -> R<Vec<(String, Symbol)>> {
    let mut out: Vec<(String, Symbol)> = vec![];
    let mut members = vec![];
    // s.id() is an id the service reported, so it is looked up as such, not resolved as a
    // qualified name from the root (which respects visibility since OpenSysML #2205)
    let listed = m.symbol_with(s.id(), &SymbolOptions { include_library_members: true, by_reported_id: true })?;
    for mb in listed.members() {
        if let Some(c) = get(m, &mb.id)? {
            members.push(c);
        }
    }
    for listing in [s.children()?, s.parts()?, s.attributes()?, members] {
        for c in listing {
            let id = norm(c.id());
            match out.iter_mut().find(|(k, _)| *k == id) {
                Some(slot) => slot.1 = c,
                None => out.push((id, c)),
            }
        }
    }
    Ok(out)
}

/// The element's Symbol, read through a path of usages when `path` is not empty, and the
/// Symbol it was read through.
fn resolve(
    m: &Model,
    element: &str,
    path: &[String],
    unnamed: Option<&(String, usize)>,
) -> R<(Symbol, Option<Symbol>)> {
    if let Some((metaclass, index)) = unnamed {
        // the index-th unnamed member of the metaclass declared in `element`
        let (cur, listed) = if let Some((through, rest)) = path.split_last() {
            let (cur, _) = resolve(m, through, rest, None)?;
            let prefix = norm(element) + "::";
            let listed: Vec<Symbol> = visible(m, &cur)?
                .into_iter()
                .map(|(_, c)| c)
                .filter(|c| c.id().starts_with(&prefix))
                .collect();
            (cur, listed)
        } else {
            let cur = sym(m, element)?;
            let listed = cur.children()?;
            (cur, listed)
        };
        let found: Vec<Symbol> = listed
            .into_iter()
            .filter(|c| {
                c.name().is_empty() && c.kind().to_lowercase().contains(&metaclass.to_lowercase())
            })
            .collect();
        return match found.get(*index) {
            Some(s) => Ok((s.clone(), Some(cur))),
            None => Err(answer(format!(
                "<unnamed {metaclass} #{index} of {element} not listed>"
            ))),
        };
    }
    let Some((first, rest)) = path.split_first() else {
        return Ok((sym(m, element)?, None));
    };
    let mut cur = sym(m, first)?;
    let mut owner = None;
    for step in rest.iter().map(String::as_str).chain([element]) {
        let want = norm(step);
        match visible(m, &cur)?.into_iter().find(|(k, _)| *k == want) {
            Some((_, next)) => {
                owner = Some(cur);
                cur = next;
            }
            None => return Err(answer(format!("<{step} not visible through {}>", cur.id()))),
        }
    }
    Ok((cur, owner))
}

/// The Symbol kind spelled as the spec metaclass: lower camel case, with `Def` for
/// `Definition` and the abbreviated words expanded (`calcDef` -> `CalculationDefinition`).
/// Abbreviations (internal/semantic/symbols/symbol.go): `calc`, `enum`, and a binding,
/// which is a BindingConnectorAsUsage.
fn metaclass_of(kind: &str) -> String {
    if kind == "bindingUsage" {
        return "BindingConnectorAsUsage".into();
    }
    let mut kind = kind.to_string();
    for (short, full) in [("calc", "calculation"), ("enum", "enumeration")] {
        if let Some(rest) = kind.strip_prefix(short) {
            if rest.starts_with(|c: char| c.is_ascii_uppercase()) {
                kind = format!("{full}{rest}");
            }
        }
    }
    if kind.ends_with("Def") {
        kind.push_str("inition");
    }
    let mut chars = kind.chars();
    match chars.next() {
        Some(c) => c.to_uppercase().chain(chars).collect(),
        None => kind,
    }
}

/// Unsupported: the Symbol API has no field for `what`. The detail notes whether the
/// standard query API offers `prop` (consulted for this note only).
fn no_symbol_field(m: &Model, element: &str, prop: &str, what: &str) -> Stop {
    let offered = m
        .query(&Query::new().scope([element]).select([prop]))
        .map(|rows| rows.iter().any(|r| r.properties.contains_key(prop)))
        .unwrap_or(false);
    let note = if offered {
        format!("available through the standard query API ({prop})")
    } else {
        "the standard query API does not offer it either".into()
    };
    Unsupported(format!("no Symbol field for {what}; {note}"))
}

fn magnitude(m: &Magnitude) -> Value {
    match m {
        Magnitude::Integer(n) => json!(n),
        Magnitude::BigInteger(n) => json!(n.to_f64()),
        Magnitude::Rational(q) => json!(q.to_f64()),
        Magnitude::Real(x) => json!(x),
    }
}

/// A scalar value as JSON; anything else as its debug form, which no expectation matches.
fn to_json(v: &OValue) -> Value {
    match v {
        OValue::Integer(n) => json!(n),
        OValue::BigInteger(n) => json!(n.to_f64()),
        OValue::Rational(q) => json!(q.to_f64()),
        OValue::Real(x) => json!(x),
        OValue::Boolean(b) => json!(b),
        OValue::Text(s) => json!(s),
        OValue::Null | OValue::Unset => Value::Null,
        other => json!(format!("<{other:?}>")),
    }
}

fn sorted<T: Ord>(mut v: Vec<T>) -> Vec<T> {
    v.sort();
    v
}

/// E10: the feature's value from the evaluation API (Evaluate), in its part def's scope
/// or with the usage as subject.
fn evaluate(m: &Model, check: &str, element: &str, subject: Option<&str>) -> Value {
    let options = match subject {
        Some(s) => EvalOptions { context: None, subject: Some(s.into()) },
        None => EvalOptions { context: Some(parent(element).into()), subject: None },
    };
    match m.evaluate(last(element), &options) {
        Err(e) => json!(format!("<evaluation failed: {e}>")),
        Ok(ev) => match (&ev.result, check == "evaluatedUnit") {
            (OValue::Quantity(q), true) => json!(q.unit),
            (OValue::Quantity(q), false) => magnitude(&q.magnitude),
            (_, true) => Value::Null,
            (v, false) => to_json(v),
        },
    }
}

/// What a path of feature names reaches in an instantiated object tree.
enum Node<'a> {
    Object(&'a Instance),
    Scalar(OValue),
    List(Vec<Node<'a>>),
    Missing(String),
}

fn instance_by_id(inst: &Instantiation, id: i64) -> Option<&Instance> {
    std::iter::once(&inst.instance)
        .chain(inst.instances())
        .find(|i| i.id() == id)
}

fn walk<'a>(inst: &'a Instantiation, path: &str) -> Node<'a> {
    let resolve = |v: &OValue| match v {
        OValue::InstanceRef(id) => instance_by_id(inst, *id)
            .map(Node::Object)
            .unwrap_or_else(|| Node::Scalar(v.clone())),
        _ => Node::Scalar(v.clone()),
    };
    let mut cur = Node::Object(&inst.instance);
    for name in path.split('.') {
        let Node::Object(obj) = cur else {
            return Node::Missing(format!("<{name}: not an object>"));
        };
        let Some(fv) = obj.feature(name) else {
            return Node::Missing(format!("<no feature {name}>"));
        };
        cur = if !fv.values().is_empty() {
            Node::List(fv.values().iter().map(resolve).collect())
        } else {
            match fv.value() {
                Some(v) => resolve(v),
                None => Node::Scalar(OValue::Null),
            }
        };
    }
    cur
}

fn describe(n: &Node) -> String {
    match n {
        Node::Object(o) => format!("<object {}>", o.type_symbol_id()),
        Node::Scalar(v) => format!("{v:?}"),
        Node::List(l) => format!("<list of {}>", l.len()),
        Node::Missing(why) => why.clone(),
    }
}

/// F10: walk `path` from the object `instantiate(root)` builds.
fn instance_check(ctx: &mut Ctx, m: &Model, c: &Value) -> R<Value> {
    let check = c["check"].as_str().unwrap();
    if check == "ownerPath" {
        return Err(Unsupported(
            "the client does not expose InstancePaths, which lists the paths to an object (issue #1959)".into(),
        ));
    }
    let root = c["element"].as_str().unwrap();
    let key = (m.hash().to_string(), root.to_string());
    let inst = ctx
        .instantiations
        .entry(key)
        .or_insert_with(|| m.instantiate(root).map_err(|e| e.to_string()));
    let inst = match inst {
        Ok(inst) => &*inst,
        Err(e) => return Ok(json!(format!("<instantiation failed: {e}>"))),
    };
    let target = walk(inst, c["path"].as_str().unwrap_or(""));
    Ok(match check {
        "instanceType" => match &target {
            Node::Object(o) => json!(o.type_symbol_id()),
            other => json!(describe(other)),
        },
        "instanceValue" => match &target {
            Node::Scalar(v) => to_json(v),
            other => json!(describe(other)),
        },
        "instanceCount" => json!(match &target {
            Node::List(l) => l.len(),
            Node::Missing(_) => 0,
            _ => 1,
        }),
        _ => {
            let other = walk(inst, c["path2"].as_str().unwrap_or(""));
            json!(matches!((&target, &other), (Node::Object(a), Node::Object(b)) if a.id() == b.id()))
        }
    })
}

struct Ctx {
    instantiations: HashMap<(String, String), Result<Instantiation, String>>,
}

/// The case's `through`: absent, one qualified name, or a path.
fn through(c: &Value) -> Vec<String> {
    match &c["through"] {
        Value::String(s) => vec![s.clone()],
        Value::Array(a) => a.iter().filter_map(|v| v.as_str().map(String::from)).collect(),
        _ => vec![],
    }
}

fn check(ctx: &mut Ctx, m: &Model, c: &Value) -> R<Value> {
    let check = c["check"].as_str().unwrap();
    let element = c["element"].as_str().unwrap();
    let path = through(c);
    let unnamed = c["unnamed"].as_object().map(|u| {
        (
            u["metaclass"].as_str().unwrap().to_string(),
            u["index"].as_u64().unwrap() as usize,
        )
    });
    let via = c["via"].as_str();

    match check {
        "instanceType" | "instanceValue" | "instanceCount" | "endIdentity" | "ownerPath" => {
            return instance_check(ctx, m, c)
        }
        "evaluatedValue" | "evaluatedUnit" => {
            return Ok(evaluate(m, check, element, c["subject"].as_str()))
        }
        "resolve" => {
            // the client's name lookup: Model::symbol resolves a qualified name from the root
            // namespace (imports, aliases, visibility); get is a lookup by reported id
            return match m.symbol(element) {
                Ok(s) => Ok(json!(s.id())),
                Err(opensysml::Error::Model(_)) => Ok(Value::Null),
                Err(e) => Err(e.into()),
            };
        }
        "isComposite" | "isReference" => return Err(no_symbol_field(m, element, check, check)),
        "entryKind" | "doKind" | "exitKind" | "isParallel" | "source" | "target"
        | "triggerPayload" | "guardKind" | "effectKind" => {
            let prop = match check {
                "entryKind" => "entryAction",
                "doKind" => "doAction",
                "exitKind" => "exitAction",
                "triggerPayload" => "triggerAction",
                "guardKind" => "guardExpression",
                "effectKind" => "effectAction",
                other => other,
            };
            return Err(no_symbol_field(m, element, prop, prop));
        }
        // reads the Symbol API has no field for: unsupported, before the element is even
        // looked up (unsupported takes precedence over not being visible)
        "shortName" => return Err(no_symbol_field(m, element, "shortName", "the short name")),
        "owner" => return Err(no_symbol_field(m, element, "owner", "the owner")),
        "isIndividual" => return Err(no_symbol_field(m, element, "isIndividual", "isIndividual")),
        "result" => return Err(no_symbol_field(m, element, "result", "the result parameter")),
        "subject" => {
            return Err(no_symbol_field(m, element, "subjectParameter", "the subject parameter"))
        }
        "documentation" | "comments" | "textualRepresentation" => {
            let prop = if check == "comments" { "comment" } else { check };
            return Err(no_symbol_field(m, element, prop, check));
        }
        "substates" => {
            let (s, _) = resolve(m, element, &path, None)?;
            let names = s
                .children()?
                .into_iter()
                .filter(|c| c.kind() == "stateUsage")
                .map(|c| c.name().to_string())
                .collect();
            return Ok(json!(sorted::<String>(names)));
        }
        "payloadTypes" | "sourceOutput" | "targetInput" => {
            let prop = match check {
                "payloadTypes" => "payloadType",
                "sourceOutput" => "sourceOutputFeature",
                _ => "targetInputFeature",
            };
            return Err(no_symbol_field(m, element, prop, &format!("the flow's {prop}")));
        }
        "sourceFeature" | "targetFeature" | "relatedFeature" => {
            if unnamed.is_some() {
                return Err(Unsupported(format!(
                    "no Symbol field for {check}; the query API cannot address an unnamed element"
                )));
            }
            return Err(no_symbol_field(m, element, check, check));
        }
        "endNames" | "endCount" if unnamed.is_none() && sym(m, element)?.kind().ends_with("Def") => {
            return Err(Unsupported(
                "the Symbol API does not mark the end features of a definition".into(),
            ));
        }
        "allSupertypes" => {
            return Err(Unsupported(
                "neither the Symbol nor the query API gives the closure of supertypes".into(),
            ))
        }
        "annotatedElement" => {
            return Err(Unsupported(
                "neither the Symbol nor the query API reports what a metadata usage annotates"
                    .into(),
            ))
        }
        "payloadArgument" | "senderArgument" | "receiverArgument" | "assignedFeature" => {
            return Err(Unsupported("the Symbol API reports no arguments of an action".into()))
        }
        "valueKind" | "valueOperator" | "valueReferences" | "valueText" => {
            return Err(Unsupported(
                "the Symbol API reports a value only as a folded constant, with no expression \
                 structure or text"
                    .into(),
            ))
        }
        "exprKind" | "instantiatedType" | "argumentCount" | "argumentReferences" | "hasResult"
        | "resultType" => {
            return Err(Unsupported(
                "the Symbol API reports neither the arguments of an action nor expression \
                 structure, so no constructor expression is reachable"
                    .into(),
            ))
        }
        "isDefault" => {
            return Err(Unsupported(
                "neither Symbol nor AttributeFacts tells a default from a bound value".into(),
            ))
        }
        "unnamedPartCount" => {
            // unnamed part usages declared in `element`, among the members the Symbol lists
            let listed: Vec<Symbol> = match path.split_last() {
                Some((through, rest)) => {
                    let (cur, _) = resolve(m, through, rest, None)?;
                    let prefix = norm(element) + "::";
                    visible(m, &cur)?
                        .into_iter()
                        .map(|(_, c)| c)
                        .filter(|c| norm(c.id()).starts_with(&prefix))
                        .collect()
                }
                None => sym(m, element)?.children()?,
            };
            let n = listed
                .iter()
                .filter(|c| c.kind() == "partUsage" && c.name().is_empty())
                .count();
            return Ok(json!(n));
        }
        _ => {}
    }

    let (s, owner) = resolve(m, element, &path, unnamed.as_ref())?;
    let meta = s.metadata();
    let names = |v: Vec<Symbol>| -> Value {
        json!(sorted(v.iter().map(|c| c.name().to_string()).collect::<Vec<_>>()))
    };
    Ok(match check {
        "name" => json!(s.name()),
        "type" => match s.type_facts() {
            None => return Err(Unsupported("no type_facts".into())),
            // the derived Feature::type, most specific first (resolved_id is the typing as written)
            Some(t) => json!(t.types.first().map_or("", |r| r.id.as_str())),
        },
        "specializations" | "subsettedFeatures" => {
            // OpenSysML's Specialization.kind spelled as the spec metaclass
            let specs: Vec<[String; 2]> = s
                .specializations()
                .into_iter()
                .map(|sp| {
                    let k = match sp.kind.as_str() {
                        "typing" => "FeatureTyping",
                        "subsets" => "Subsetting",
                        "redefines" => "Redefinition",
                        "references" => "ReferenceSubsetting",
                        "specializes" => "Subclassification",
                        other => other,
                    };
                    [k.to_string(), sp.target_id]
                })
                .collect();
            if check == "specializations" {
                json!(sorted(specs))
            } else {
                let subsetted = specs
                    .into_iter()
                    .filter(|[k, _]| {
                        matches!(k.as_str(), "Subsetting" | "Redefinition" | "ReferenceSubsetting")
                    })
                    .map(|[_, t]| t)
                    .collect();
                json!(sorted::<String>(subsetted))
            }
        }
        "types" => match s.type_facts() {
            None => return Err(Unsupported("no type_facts".into())),
            // the derived Feature::type (resolved_id is the typing as written)
            Some(t) => json!(sorted(t.types.iter().map(|r| r.id.clone()).collect::<Vec<_>>())),
        },
        "idRoundTrip" => json!(m.get(s.id())?.is_some_and(|again| again.id() == s.id())),
        "directGenerals" => json!(sorted::<String>(
            s.specializations()
                .into_iter()
                .filter(|sp| sp.kind == "specializes")
                .map(|sp| sp.target_id)
                .collect()
        )),
        "ownedFeatureNames" => names(
            s.children()?
                .into_iter()
                .filter(|c| !c.kind().ends_with("Def"))
                .collect(),
        ),
        "inheritedFeatureNames" => {
            // members the Symbol lists (children, parts, attributes, members) that it does not
            // own, and that are features: Type::inheritedFeature, not inheritedMembership (a doc
            // or comment is not)
            let prefix = norm(s.id()) + "::";
            names(
                visible(m, &s)?
                    .into_iter()
                    .filter(|(id, c)| !id.starts_with(&prefix) && is_feature_kind(c.kind()))
                    .map(|(_, c)| c)
                    .collect(),
            )
        }
        "redefinitions" => {
            let mut out: Vec<[String; 2]> = vec![];
            for c in s.children()? {
                for sp in c.specializations() {
                    if sp.kind == "redefines" {
                        out.push([c.id().to_string(), sp.target_id]);
                    }
                }
            }
            json!(sorted(out))
        }
        "metadataDefs" | "metadataValue" => {
            // annotations an element lists: its metadata-usage children
            let symbols: Vec<Symbol> = s
                .children()?
                .into_iter()
                .filter(|c| c.kind() == "metadataUsage")
                .collect();
            if check == "metadataDefs" {
                let mut defs: Vec<String> = symbols
                    .iter()
                    .filter_map(|c| c.type_facts().map(|t| t.resolved_id))
                    .collect();
                defs.sort();
                defs.dedup();
                json!(defs)
            } else {
                let Some(first) = symbols.first() else {
                    return Ok(json!(format!("<no annotation of {} readable as a Symbol>", s.id())));
                };
                first
                    .attribute_facts()?
                    .into_iter()
                    .find(|f| f.name == "severity")
                    .and_then(|f| f.value)
                    .map_or(Value::Null, |v| to_json(&v))
            }
        }
        "kind" => json!(metaclass_of(s.kind())),
        // Symbol metadata carries `abstract` / `variation: true` when they hold, nothing otherwise
        "isAbstract" => json!(meta.get("abstract").is_some_and(|v| v == "true")),
        "isVariation" => json!(meta.get("variation").is_some_and(|v| v == "true")),
        "referenceTarget" => {
            if via == Some("type") {
                s.type_facts().map_or(Value::Null, |t| json!(t.resolved_id))
            } else {
                s.specializations()
                    .into_iter()
                    .find(|sp| sp.kind == "subsets")
                    .map_or(Value::Null, |sp| json!(sp.target_id))
            }
        }
        "parameters" => {
            // members the Symbol lists that carry a direction in their metadata
            let mut out: Vec<[String; 2]> = vec![];
            for (_, c) in visible(m, &s)? {
                if let Some(d) = c.metadata().get("direction") {
                    out.push([d.clone(), c.name().to_string()]);
                }
            }
            json!(sorted(out))
        }
        // variant usages carry `variant: true` in their metadata
        "variants" => names(
            s.children()?
                .into_iter()
                .filter(|c| c.metadata().get("variant").is_some_and(|v| v == "true"))
                .collect(),
        ),
        "typeIsConjugated" => match s.type_facts() {
            Some(t) if !t.resolved_id.is_empty() => {
                // a conjugated port definition is named "~" + its original's name (SysML spec)
                json!(sym(m, &t.resolved_id)?.name().starts_with('~'))
            }
            _ => Value::Null,
        },
        // the member's direction as the Symbol reports it when listed through the port
        "direction" => meta.get("direction").map_or(Value::Null, |d| json!(d)),
        "multiplicity" => match s.multiplicity() {
            None => Value::Null,
            Some(mu) => {
                let lower = if !mu.lower.is_empty() {
                    mu.lower
                } else if mu.upper == "*" {
                    "0".into()
                } else {
                    mu.upper.clone()
                };
                json!(format!("{lower}..{}", mu.upper))
            }
        },
        "endCount" | "endNames" | "endReferences" => {
            let ends: Vec<Symbol> = s
                .children()?
                .into_iter()
                .filter(|c| c.kind() == "connectorEnd")
                .collect();
            match check {
                "endCount" => json!(ends.len()),
                "endNames" => json!(ends.iter().map(|e| e.name()).collect::<Vec<_>>()),
                // an end's reference is reported, if at all, as a subsets/references specialization
                _ => json!(ends
                    .iter()
                    .map(|e| e
                        .specializations()
                        .into_iter()
                        .filter(|sp| sp.kind == "subsets" || sp.kind == "references")
                        .map(|sp| sp.target_id)
                        .collect::<Vec<_>>())
                    .collect::<Vec<_>>()),
            }
        }
        "value" => {
            // a feature's value is reported by its owner's attribute_facts()
            let owner = match owner {
                Some(o) => o,
                None => sym(m, parent(element))?,
            };
            match owner.attribute_facts()?.into_iter().find(|f| f.name == s.name()) {
                None => json!(format!("<{} not in attribute_facts of {}>", s.name(), owner.id())),
                Some(f) => f.value.map_or(Value::Null, |v| to_json(&v)),
            }
        }
        other => return Err(Error(format!("unknown check {other}"))),
    })
}

fn matches(actual: &Value, want: &Value) -> bool {
    match (actual.as_f64(), want.as_f64()) {
        (Some(a), Some(w)) => a == w,
        _ => actual == want,
    }
}

/// Parse a model; one the MDK reports errors for makes every case that uses it an error.
fn load(conn: &Connection, file: &str) -> Result<Model, String> {
    let text = fs::read_to_string(root().join("../data").join(file)).map_err(|e| e.to_string())?;
    let model = conn
        .parse_content(&text, &ParseOptions::default())
        .map_err(|e| format!("model not parsed: {e}"))?;
    let errors: Vec<String> = model
        .diagnostics()
        .iter()
        .filter(|d| d.severity == "error")
        .take(2)
        .map(|d| format!("line {}: {}", d.span.as_ref().map_or(0, |s| s.start_line), d.message))
        .collect();
    if !errors.is_empty() {
        return Err(format!("model rejected: {}", errors.join("; ")));
    }
    Ok(model)
}

#[test]
fn matrices() {
    // The service binary is the locally built one, never a downloaded release.
    if std::env::var_os("OPENSYSML_GRPC_BINARY").is_none() {
        std::env::set_var(
            "OPENSYSML_GRPC_BINARY",
            root().join("../../OpenSysML/bin/sysml-grpc"),
        );
    }
    let conn = Connection::private().expect("start sysml-grpc (OPENSYSML_GRPC_BINARY)");

    let mut files: Vec<_> = fs::read_dir(root().join("../data/cases"))
        .unwrap()
        .map(|e| e.unwrap().path())
        .filter(|p| p.extension().is_some_and(|x| x == "json"))
        .collect();
    files.sort();
    let specs: Vec<Value> = files
        .iter()
        .map(|f| serde_json::from_str(&fs::read_to_string(f).unwrap()).unwrap())
        .collect();

    let mut models: HashMap<String, Result<Model, String>> = HashMap::new();
    let mut ctx = Ctx { instantiations: HashMap::new() };
    let mut rows: Vec<[String; 5]> = vec![];
    let mut failed = vec![];
    for s in &specs {
        let matrix = s["matrix"].as_str().unwrap();
        for c in s["cases"].as_array().unwrap() {
            let id = c["id"].as_str().unwrap();
            let file = c["model"].as_str().or(s["model"].as_str()).unwrap();
            let model = models
                .entry(file.to_string())
                .or_insert_with(|| load(&conn, file));
            let result = match model {
                Err(why) => Err(Error(why.clone())),
                Ok(m) => check(&mut ctx, m, c),
            };
            let result = match result {
                Err(Answer(v)) => Ok(v),
                other => other,
            };
            let (outcome, detail) = match result {
                Err(Error(e)) => ("error", e),
                Err(Unsupported(why)) => ("unsupported", why),
                Err(Answer(_)) => unreachable!(),
                Ok(v) => {
                    let accepted = c["accept"]
                        .as_array()
                        .is_some_and(|a| a.iter().any(|w| matches(&v, w)));
                    if matches(&v, &c["expect"]) || accepted {
                        ("pass", String::new())
                    } else {
                        let what = format!("{} {}", c["check"].as_str().unwrap(), c["element"].as_str().unwrap());
                        ("fail", format!("{what}: got {v}, want {}", c["expect"]))
                    }
                }
            };
            println!("{id} {outcome} {detail}");
            if outcome == "fail" || outcome == "error" {
                failed.push(id.to_string());
            }
            rows.push([SUITE.into(), matrix.into(), id.into(), outcome.into(), detail]);
        }
    }
    write_csv(&rows);
    assert!(failed.is_empty(), "{} cases failed or errored", failed.len());
}

fn write_csv(rows: &[[String; 5]]) {
    let dir = std::env::var("RESULTS_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|_| root().join("../results"));
    fs::create_dir_all(&dir).unwrap();
    let q = |s: &str| format!("\"{}\"", s.replace('"', "\"\"").replace('\n', " "));
    let mut out = String::from("suite,matrix,id,outcome,detail\n");
    for r in rows {
        out.push_str(&r.iter().map(|c| q(c)).collect::<Vec<_>>().join(","));
        out.push('\n');
    }
    fs::write(dir.join(format!("{SUITE}.csv")), out).unwrap();
}
