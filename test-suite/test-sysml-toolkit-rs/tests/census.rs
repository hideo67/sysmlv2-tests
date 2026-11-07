//! The derived-property census (data/gen_census.py) against sysml-toolkit's `ResolvedModel`,
//! read as the compatibility reader of suite sysml-toolkit-rs reads a property: owned through
//! `element_properties` when the element carries it, else `derived(element, "<spec name>")`;
//! under the closure policy with the implied library heritage. Runs only with CENSUS set
//! (run-census.sh); writes results/census-sysml-toolkit-rs.json.
use serde_json::{json, Map, Value};
use std::collections::{BTreeMap, HashSet};
use std::fs;
use std::path::PathBuf;
use sysmlv2_parser::json::{ClosurePolicy, Derived, DerivedValue, ElementRef, ResolvedModel};
use sysmlv2_parser::model::Model;

fn root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}

/// carriers, non-empty, empty, unanswered, error
type Counts = [u64; 5];

#[derive(Default)]
struct Census {
    counts: BTreeMap<String, BTreeMap<String, Counts>>,
    notes: BTreeMap<String, String>,
    unknown: BTreeMap<String, u64>,
    seen: HashSet<ElementRef>,
}

fn owned_empty(v: &Value) -> bool {
    match v {
        Value::Null => true,
        Value::Array(a) => a.is_empty(),
        Value::String(s) => s.is_empty(),
        _ => false,
    }
}

fn derived_empty(v: &DerivedValue) -> bool {
    match v {
        DerivedValue::Null => true,
        DerivedValue::Elements(x) => x.is_empty(),
        DerivedValue::References(x) => x.is_empty(),
        DerivedValue::Strings(x) => x.is_empty(),
        DerivedValue::Literals(x) => x.is_empty(),
        _ => false,
    }
}

impl Census {
    /// e, its non-implied owned relationships and their owned related elements, transitively,
    /// read off the compact rows (`element_properties` leaves the ownership properties out).
    fn walk(&mut self, rm: &mut ResolvedModel, metaclasses: &Map<String, Value>, rows: &BTreeMap<String, Value>, start: &str) {
        let ids = |v: Option<&Value>| -> Vec<String> {
            match v {
                Some(Value::Array(a)) => a.iter().filter_map(|r| r["@id"].as_str().map(String::from)).collect(),
                Some(o @ Value::Object(_)) => o["@id"].as_str().map(String::from).into_iter().collect(),
                _ => vec![],
            }
        };
        let mut todo = vec![start.to_string()];
        while let Some(id) = todo.pop() {
            let Some(e) = rm.element_by_id(&id) else { continue };
            if !self.seen.insert(e) {
                continue;
            }
            self.measure(rm, metaclasses, e);
            let Some(row) = rows.get(&id) else { continue };
            for r in ids(row.get("ownedRelationship")).into_iter().rev() {
                let Some(rrow) = rows.get(&r) else { continue };
                if rrow.get("isImplied").and_then(Value::as_bool) == Some(true) {
                    continue;
                }
                todo.extend(ids(rrow.get("ownedRelatedElement")));
                todo.push(r);
            }
        }
    }

    fn measure(&mut self, rm: &mut ResolvedModel, metaclasses: &Map<String, Value>, e: ElementRef) {
        let metaclass = rm.element_type(e).to_string();
        let Some(keys) = metaclasses.get(&metaclass).and_then(Value::as_array) else {
            *self.unknown.entry(metaclass).or_default() += 1;
            return;
        };
        let owned = rm.element_properties(e);
        for k in keys {
            let key = k.as_str().unwrap();
            let name = &key[key.find("::").unwrap() + 2..];
            let n = self.counts.entry(key.into()).or_default().entry(metaclass.clone()).or_default();
            n[0] += 1;
            if let Some(v) = owned.get(name) {
                n[if owned_empty(v) { 2 } else { 1 }] += 1;
                continue;
            }
            match rm.derived(e, name) {
                Derived::Value(v) => n[if derived_empty(&v) { 2 } else { 1 }] += 1,
                Derived::NotComputed => {
                    n[3] += 1;
                    self.notes.entry(key.into()).or_insert_with(|| "not computed by the toolkit".into());
                }
                Derived::NotDeclared => {
                    n[3] += 1;
                    self.notes.entry(key.into()).or_insert_with(|| format!("not declared on {metaclass}"));
                }
            }
        }
    }
}

#[test]
fn census() {
    if std::env::var_os("CENSUS").is_none() {
        eprintln!("CENSUS not set; skipped");
        return;
    }
    let spec: Value =
        serde_json::from_str(&fs::read_to_string(root().join("../data/census/derived-properties.json")).unwrap()).unwrap();
    let metaclasses = spec["metaclasses"].as_object().unwrap();
    let mut corpora = Map::new();
    for (corpus, files) in spec["corpora"].as_object().unwrap() {
        let mut model = Model::new();
        model
            .load_library_dir(&root().join("../../sysml-toolkit/spec-refs/SysML-v2-Release/sysml.library"))
            .expect("standard library (initialise the sysml-toolkit submodule spec-refs/SysML-v2-Release)");
        let files: Vec<&str> = files.as_array().unwrap().iter().map(|f| f.as_str().unwrap()).collect();
        for f in &files {
            model.add_source(*f, &fs::read_to_string(root().join("..").join(f)).unwrap());
        }
        let mut with_errors = vec![];
        for i in 0..model.unit_count() {
            if model.is_library_unit(i) {
                continue;
            }
            let unit = &model.units()[i];
            if unit.diagnostics.iter().any(|d| matches!(d.severity, sysmlv2_parser::diag::Severity::Error)) {
                with_errors.push(unit.name.clone());
            }
        }
        let mut rm = ResolvedModel::build(&model);
        rm.set_closure_policy(ClosurePolicy::Closure { include_implied: true });
        // the compact rows by id; each document's root namespace is the user element that
        // neither a relationship owns nor is itself a relationship
        let rows: BTreeMap<String, Value> = rm
            .built_compact_rows()
            .expect("compact rows of the build")
            .elements()
            .filter_map(|row| row["@id"].as_str().map(String::from).map(|id| (id, row)))
            .collect();
        let roots: Vec<String> = rows
            .iter()
            .filter(|(_, row)| {
                ["owningRelationship", "owningRelatedElement"].iter().all(|k| row.get(*k).map_or(true, Value::is_null))
            })
            .map(|(id, _)| id.clone())
            .collect();
        let mut census = Census::default();
        for id in &roots {
            census.walk(&mut rm, metaclasses, &rows, id);
        }
        let counts: Map<String, Value> = census
            .counts
            .iter()
            .map(|(k, m)| (k.clone(), json!(m.iter().map(|(mc, n)| (mc.clone(), json!(n))).collect::<Map<_, _>>())))
            .collect();
        corpora.insert(
            corpus.clone(),
            json!({
                "files": files.len(),
                "filesWithErrors": with_errors,
                "elements": census.seen.len(),
                "counts": counts,
                "notes": census.notes,
                "unknownMetaclasses": census.unknown,
            }),
        );
        println!("{corpus}: {} elements", census.seen.len());
    }
    let dir = std::env::var("RESULTS_DIR").map(PathBuf::from).unwrap_or_else(|_| root().join("../results"));
    fs::create_dir_all(&dir).unwrap();
    let out = json!({"suite": "sysml-toolkit-rs", "corpora": corpora});
    fs::write(dir.join("census-sysml-toolkit-rs.json"), serde_json::to_string_pretty(&out).unwrap()).unwrap();
}
