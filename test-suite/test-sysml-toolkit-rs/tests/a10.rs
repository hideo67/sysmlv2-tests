//! Matrix A10 (part usages) against sysml-toolkit's model API, read through the
//! full-form interchange JSON (`model_to_full_json`).
use serde_json::Value;
use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;
use sysmlv2_parser::full::model_to_full_json;
use sysmlv2_parser::model::Model;

enum Outcome {
    Value(Value),
    Unsupported(String),
}

fn data() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../data")
}

struct Doc {
    by_qn: HashMap<String, Value>,
    by_id: HashMap<String, Value>,
}

impl Doc {
    fn load(model_file: &str) -> Doc {
        let src = fs::read_to_string(data().join(model_file)).unwrap();
        let mut model = Model::new();
        model.add_source(model_file, &src);
        let json = model_to_full_json(&model);
        let mut by_qn = HashMap::new();
        let mut by_id = HashMap::new();
        for e in json.as_array().expect("array of elements") {
            by_id.insert(e["@id"].as_str().unwrap().to_string(), e.clone());
            if let Some(q) = e.get("qualifiedName").and_then(|q| q.as_str()) {
                by_qn.insert(q.to_string(), e.clone());
            }
        }
        Doc { by_qn, by_id }
    }
    fn resolve(&self, v: &Value) -> &Value {
        &self.by_id[v["@id"].as_str().unwrap()]
    }
}

fn check(doc: &Doc, check: &str, element: &str, through: Option<&str>) -> Outcome {
    let qn = |v: &Value| doc.resolve(v)["qualifiedName"].as_str().map(String::from);
    if check == "unnamedPartCount" {
        // unnamed parts declared in `element`, as visible from `through` (inherited) or `element` itself
        let src = &doc.by_qn[through.unwrap_or(element)];
        let key = if through.is_some() { "inheritedFeature" } else { "ownedMember" };
        let n = src[key].as_array().unwrap().iter().map(|f| doc.resolve(f))
            .filter(|f| f["@type"] == "PartUsage" && f["declaredName"].is_null())
            .filter(|f| f["owner"].is_object() && doc.resolve(&f["owner"])["qualifiedName"] == element)
            .count();
        return Outcome::Value(Value::from(n));
    }
    let e = match through {
        None => doc.by_qn.get(element),
        Some(t) => doc.by_qn[t]["inheritedFeature"].as_array().unwrap().iter()
            .find(|f| qn(f).as_deref() == Some(element)).map(|f| doc.resolve(f)),
    };
    let Some(e) = e else {
        return Outcome::Value(Value::from(format!("<{element} not visible through {}>", through.unwrap_or("-"))));
    };
    match check {
        "name" => Outcome::Value(e["declaredName"].clone()),
        "type" => Outcome::Value(doc.resolve(&e["type"][0])["qualifiedName"].clone()),
        "isComposite" => Outcome::Value(e["isComposite"].clone()),
        "isReference" => Outcome::Value(e["isReference"].clone()),
        other => panic!("unknown check {other}"),
    }
}

#[test]
fn matrix_a10() {
    let spec: Value =
        serde_json::from_str(&fs::read_to_string(data().join("cases/A10.json")).unwrap()).unwrap();
    let doc = Doc::load(spec["model"].as_str().unwrap());
    let (mut pass, mut fail, mut unsupported) = (0, vec![], 0);
    let mut rows: Vec<[String; 5]> = vec![];
    let mut row = |id: &str, outcome: &str, detail: String| {
        rows.push(["sysml-toolkit-rs".into(), "A10".into(), id.into(), outcome.into(), detail]);
    };
    for c in spec["cases"].as_array().unwrap() {
        let id = c["id"].as_str().unwrap();
        match check(&doc, c["check"].as_str().unwrap(), c["element"].as_str().unwrap(), c["through"].as_str()) {
            Outcome::Unsupported(why) => {
                unsupported += 1;
                row(id, "unsupported", why.clone());
                println!("{id} UNSUPPORTED: {why}");
            }
            Outcome::Value(v) if v == c["expect"] => {
                pass += 1;
                row(id, "pass", String::new());
                println!("{id} PASS");
            }
            Outcome::Value(v) => {
                println!("{id} FAIL: got {v}, want {}", c["expect"]);
                row(id, "fail", format!("{} {}: got {v}, want {}", c["check"], c["element"], c["expect"]));
                fail.push(id.to_string());
            }
        }
    }
    write_csv(&rows);
    println!("pass={pass} fail={} unsupported={unsupported}", fail.len());
    assert!(fail.is_empty(), "failed: {fail:?}");
}

fn write_csv(rows: &[[String; 5]]) {
    let dir = std::env::var("RESULTS_DIR").map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../results"));
    fs::create_dir_all(&dir).unwrap();
    let q = |s: &str| format!("\"{}\"", s.replace('"', "\"\"").replace('\n', " "));
    let mut out = String::from("suite,matrix,id,outcome,detail\n");
    for r in rows {
        out.push_str(&r.iter().map(|c| q(c)).collect::<Vec<_>>().join(","));
        out.push('\n');
    }
    fs::write(dir.join("sysml-toolkit-rs.csv"), out).unwrap();
}
