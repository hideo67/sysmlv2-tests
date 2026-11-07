// Every matrix in data/cases/*.json against the OpenSysML TypeScript client
// (client/node), in one of two backends, chosen by OPENSYSML_TS_BACKEND:
//   grpc (default; suite opensysml-ts): connect(), a private child of the locally
//     built sysml-grpc;
//   wasm (suite opensysml-ts-wasm): connectWasm(), the locally built sysml-wasm
//     WebAssembly module, with no service process.
//
// Only the Symbol API is used: it is OpenSysML's element API, the counterpart of the
// Pilot's EMF model and sysml-toolkit's ResolvedModel (DISCUSSIONS.md, Step 5 decision).
// When the Symbol API has no field for a read, the result is unsupported, and the detail
// says whether the standard SysML v2 API & Services query API offers the property; the
// query API is consulted for that note only, never for a value.
//
// A TS ModelSymbol has the shape of the Go client's Symbol (child ids, and the attribute
// facts the service sends), and Model.symbol() takes the service's answer as Go's
// LookupSymbol does, so the reads follow the Go adapter.
import { readFileSync, readdirSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, join, resolve as resolvePath } from "node:path";
import { fileURLToPath } from "node:url";
import {
  connect,
  connectWasm,
  MissingCapabilityError,
  SymbolNotFoundError,
} from "@openmbee/opensysml";
import type { Connection, Model, ModelSymbol, SysMLValue, InstanceTree, Instance } from "@openmbee/opensysml";

const HERE = dirname(fileURLToPath(import.meta.url));
const DATA = join(HERE, "..", "data");
const OPENSYSML = join(HERE, "..", "..", "OpenSysML");

const BACKEND = process.env.OPENSYSML_TS_BACKEND || "grpc";
if (BACKEND !== "grpc" && BACKEND !== "wasm") {
  throw new Error(`OPENSYSML_TS_BACKEND=${BACKEND}: expected grpc or wasm`);
}
const SUITE = BACKEND === "wasm" ? "opensysml-ts-wasm" : "opensysml-ts";

type Json = null | boolean | number | string | Json[];

interface Case {
  id: string;
  check: string;
  element: string;
  through?: string | string[];
  expect: Json;
  accept?: Json[];
  via?: string;
  model?: string;
  subject?: string;
  path?: string;
  path2?: string;
  unnamed?: { metaclass: string; index: number };
}

/** Why a check stops before its last line: an early answer, or an unsupported read. */
class Answer {
  readonly value: Json;
  constructor(value: Json) {
    this.value = value;
  }
}
class Unsupported {
  readonly why: string;
  constructor(why: string) {
    this.why = why;
  }
}

/** Qualified names compared without quoting: OpenSysML spells `CmdPort::~CmdPort`
 * where the textual notation quotes `CmdPort::'~CmdPort'`. */
const norm = (qn: string): string => qn.replaceAll("'", "");
const parent = (qn: string): string => (qn.includes("::") ? qn.slice(0, qn.lastIndexOf("::")) : "");
const last = (qn: string): string => (qn.includes("::") ? qn.slice(qn.lastIndexOf("::") + 2) : qn);
const byString = (a: string, b: string): number => (a < b ? -1 : a > b ? 1 : 0);
const sortPairs = (v: string[][]): string[][] => v.sort((a, b) => byString(a.join(" "), b.join(" ")));

/** The client's name lookup, Model.symbol(qualified name), as written or unquoted. */
async function lookup(m: Model, qn: string): Promise<ModelSymbol | undefined> {
  for (const name of [qn, norm(qn)]) {
    try {
      return await m.symbol(name);
    } catch (error) {
      if (!(error instanceof SymbolNotFoundError)) {
        throw error;
      }
    }
  }
  return undefined;
}

async function sym(m: Model, qn: string): Promise<ModelSymbol> {
  const s = await lookup(m, qn);
  if (s === undefined) {
    throw new Answer(`<no symbol ${qn}>`);
  }
  return s;
}

/** Symbol kinds whose words are abbreviated (internal/semantic/symbols/symbol.go): `calc`,
 * `enum`, and a binding, which is a BindingConnectorAsUsage. Spelled as the spec metaclass:
 * `Def` for `Definition` and the abbreviations expanded (`calcDef` -> `CalculationDefinition`). */
function metaclassOf(kind: string): string {
  if (kind === "") {
    return "";
  }
  if (kind === "bindingUsage") {
    return "BindingConnectorAsUsage";
  }
  for (const [short, full] of [["calc", "calculation"], ["enum", "enumeration"]]) {
    const rest = kind.slice(short.length);
    if (kind.startsWith(short) && /^[A-Z]/.test(rest)) {
      kind = full + rest;
    }
  }
  if (kind.endsWith("Def")) {
    kind += "inition";
  }
  return kind[0].toUpperCase() + kind.slice(1);
}

/** Unsupported: the Symbol API has no field for `what`. The detail notes whether the standard
 * query API offers `prop` (consulted for this note only). sysml-wasm serves no Query at all. */
async function noSymbolField(m: Model, element: string, prop: string, what: string): Promise<Unsupported> {
  let note = "the standard query API does not offer it either";
  try {
    const rows = await m.query({ scope: [element], select: [prop] });
    if (rows.some((r) => prop in r.properties)) {
      note = `available through the standard query API (${prop})`;
    }
  } catch (error) {
    if (error instanceof MissingCapabilityError) {
      note = "the standard query API is not served by this backend (sysml-wasm has no Query)";
    }
  }
  return new Unsupported(`no Symbol field for ${what}; ${note}`);
}

/** A scalar value as JSON; anything else as a text no expectation matches. */
function toJson(v: SysMLValue | undefined): Json {
  if (v === undefined) {
    return null;
  }
  switch (v.kind) {
    case "int":
      return Number(v.value);
    case "real":
      return v.value;
    case "rational":
      return Number(v.numerator) / Number(v.denominator);
    case "boolean":
      return v.value;
    case "string":
      return v.value;
    case "null":
    case "unset":
    case "absent":
      return null;
    default:
      return `<${v.kind} value>`;
  }
}

function magnitude(v: SysMLValue & { kind: "quantity" }): Json {
  const mg = v.magnitude;
  switch (mg.kind) {
    case "int":
      return Number(mg.value);
    case "real":
      return mg.value;
    default:
      return Number(mg.numerator) / Number(mg.denominator);
  }
}

/** E10: the feature's value from the evaluation API (Model.eval), in its part def's scope
 * or with the usage as subject. */
async function evaluate(m: Model, c: Case): Promise<Json> {
  let v: SysMLValue;
  try {
    v = await m.eval(last(c.element), c.subject ? { subject: c.subject } : { context: parent(c.element) });
  } catch (error) {
    return `<evaluation failed: ${error}>`;
  }
  if (c.check === "evaluatedUnit") {
    return v.kind === "quantity" ? v.unit : null;
  }
  return v.kind === "quantity" ? magnitude(v) : toJson(v);
}

/** What a path of feature names reaches in an instantiated object tree. */
type Node =
  | { kind: "object"; obj: Instance }
  | { kind: "scalar"; value: SysMLValue }
  | { kind: "list"; items: Node[] }
  | { kind: "missing"; why: string };

function walk(tree: InstanceTree, path: string): Node {
  const resolve = (v: SysMLValue): Node => {
    const obj = v.kind === "instance" ? tree.byId(v.id) : undefined;
    return obj ? { kind: "object", obj } : { kind: "scalar", value: v };
  };
  let cur: Node = { kind: "object", obj: tree.root };
  for (const name of path.split(".")) {
    if (cur.kind !== "object") {
      return { kind: "missing", why: `<${name}: not an object>` };
    }
    const fv = cur.obj.get(name);
    if (fv === undefined) {
      return { kind: "missing", why: `<no feature ${name}>` };
    }
    if (fv.kind === "error") {
      return { kind: "missing", why: `<feature ${name}: ${fv.error}>` };
    }
    cur = fv.kind === "many" ? { kind: "list", items: fv.values.map(resolve) } : resolve(fv.value);
  }
  return cur;
}

const describe = (n: Node): string =>
  n.kind === "object" ? `<object ${n.obj.typeId}>`
  : n.kind === "scalar" ? `<${n.value.kind} value>`
  : n.kind === "list" ? `<list of ${n.items.length}>`
  : n.why;

const instantiations = new Map<string, InstanceTree | string>();

/** F10: walk `path` from the object Model.instantiate(root) builds. */
async function instanceCheck(m: Model, c: Case): Promise<Json> {
  if (c.check === "ownerPath") {
    throw new Unsupported("the client does not expose InstancePaths, which lists the paths to an object (issue #1959)");
  }
  const key = `${m.hash} ${c.element}`;
  if (!instantiations.has(key)) {
    try {
      instantiations.set(key, await m.instantiate(c.element));
    } catch (error) {
      instantiations.set(key, `<instantiation failed: ${error}>`);
    }
  }
  const tree = instantiations.get(key)!;
  if (typeof tree === "string") {
    return tree;
  }
  const target = walk(tree, c.path ?? "");
  switch (c.check) {
    case "instanceType":
      return target.kind === "object" ? target.obj.typeId : describe(target);
    case "instanceValue":
      return target.kind === "scalar" ? toJson(target.value) : describe(target);
    case "instanceCount":
      return target.kind === "list" ? target.items.length : target.kind === "object" ? 1 : 0;
  }
  const other = walk(tree, c.path2 ?? "");
  return target.kind === "object" && other.kind === "object" && target.obj.id === other.obj.id;
}

/** The symbols of `ids`, each looked up by its id; one the client cannot find is left out. */
async function symbols(m: Model, ids: readonly string[]): Promise<ModelSymbol[]> {
  const out: ModelSymbol[] = [];
  for (const id of ids) {
    const s = await lookup(m, id);
    if (s !== undefined) {
      out.push(s);
    }
  }
  return out;
}

async function check(m: Model, c: Case): Promise<Json> {
  const through = c.through === undefined ? [] : typeof c.through === "string" ? [c.through] : c.through;
  switch (c.check) {
    case "instanceType": case "instanceValue": case "instanceCount": case "endIdentity": case "ownerPath":
      return instanceCheck(m, c);
    case "evaluatedValue": case "evaluatedUnit":
      return evaluate(m, c);
    case "resolve": {
      // the client's name lookup: Model.symbol(qualified name)
      const s = await lookup(m, c.element);
      return s === undefined ? null : s.id;
    }
    case "entryKind": case "doKind": case "exitKind": case "isParallel": case "source": case "target":
    case "triggerPayload": case "guardKind": case "effectKind": {
      const prop = ({ entryKind: "entryAction", doKind: "doAction", exitKind: "exitAction",
        triggerPayload: "triggerAction", guardKind: "guardExpression", effectKind: "effectAction" } as Record<string, string>)[c.check] ?? c.check;
      throw await noSymbolField(m, c.element, prop, prop);
    }
    case "payloadTypes": case "sourceOutput": case "targetInput": {
      const prop = ({ payloadTypes: "payloadType", sourceOutput: "sourceOutputFeature", targetInput: "targetInputFeature" } as Record<string, string>)[c.check];
      throw await noSymbolField(m, c.element, prop, `the flow's ${prop}`);
    }
    // reads the Symbol API has no field for: unsupported, before the element is even looked up
    // (unsupported takes precedence over not being visible)
    case "shortName": throw await noSymbolField(m, norm(c.element), "shortName", "the short name");
    case "owner": throw await noSymbolField(m, norm(c.element), "owner", "the owner");
    case "isIndividual": throw await noSymbolField(m, norm(c.element), "isIndividual", "isIndividual");
    case "result": throw await noSymbolField(m, norm(c.element), "result", "the result parameter");
    case "subject": throw await noSymbolField(m, norm(c.element), "subjectParameter", "the subject parameter");
    case "documentation": case "comments": case "textualRepresentation":
      throw await noSymbolField(m, norm(c.element), c.check === "comments" ? "comment" : c.check, c.check);
    case "isComposite": case "isReference":
      throw await noSymbolField(m, c.element, c.check, c.check);
    case "sourceFeature": case "targetFeature": case "relatedFeature":
      if (c.unnamed) {
        throw new Unsupported(`no Symbol field for ${c.check}; the query API cannot address an unnamed element`);
      }
      throw await noSymbolField(m, c.element, c.check, c.check);
    case "allSupertypes":
      throw new Unsupported("neither the Symbol nor the query API gives the closure of supertypes");
    case "annotatedElement":
      throw new Unsupported("neither the Symbol nor the query API reports what a metadata usage annotates");
    case "payloadArgument": case "senderArgument": case "receiverArgument": case "assignedFeature":
      throw new Unsupported("the Symbol API reports no arguments of an action");
    case "valueKind": case "valueOperator": case "valueReferences": case "valueText":
      throw new Unsupported("the Symbol API reports a value only as a folded constant, with no expression structure or text");
    case "exprKind": case "instantiatedType": case "argumentCount": case "argumentReferences": case "hasResult": case "resultType":
      throw new Unsupported("the Symbol API reports neither the arguments of an action nor expression structure, " +
        "so no constructor expression is reachable");
    case "isDefault":
      throw new Unsupported("neither Symbol nor AttributeFacts tells a default from a bound value");
    case "unnamedPartCount": {
      // unnamed part usages declared in c.element, among the children the Symbol lists
      const scope = norm(through.length > 0 ? through[through.length - 1] : c.element);
      const o = await sym(m, scope);
      const prefix = norm(c.element) + "::";
      return (await o.children()).filter((ch) => ch.name === "" && ch.kind === "partUsage" && ch.id.startsWith(prefix)).length;
    }
  }

  let owner = parent(c.element);
  let id = norm(c.element);
  if (through.length > 0) {
    // each step is read as a member the previous Symbol lists: as a child, or (for
    // attributes, own and inherited) in its attribute facts
    let cur = await sym(m, norm(through[0]));
    const steps = [...through.slice(1), ...(c.unnamed ? [] : [c.element])];
    for (const raw of steps) {
      const step = norm(raw);
      const visible = cur.childIds.includes(step) || cur.attributes.some((a) => a.name === last(step));
      if (!visible) {
        return `<${step} not visible through ${cur.id}>`;
      }
      owner = cur.id;
      cur = await sym(m, step);
    }
  }
  if (c.unnamed) {
    // the index-th unnamed member of the metaclass declared in c.element
    const o = await sym(m, norm(through.length > 0 ? through[through.length - 1] : c.element));
    const meta = c.unnamed.metaclass.toLowerCase();
    const found = (await o.children()).filter((ch) => ch.name === "" && ch.kind.toLowerCase().includes(meta));
    if (found.length <= c.unnamed.index) {
      return `<unnamed ${c.unnamed.metaclass} #${c.unnamed.index} of ${c.element} not listed>`;
    }
    id = found[c.unnamed.index].id;
  }
  const s = await sym(m, id);

  switch (c.check) {
    case "name":
      return s.name;
    case "type":
      if (s.type === undefined) throw new Unsupported("no type info");
      return s.type.resolvedId;
    case "specializations": case "subsettedFeatures": {
      // OpenSysML's Specialization kind spelled as the spec metaclass
      const kinds: Record<string, string> = { typing: "FeatureTyping", subsets: "Subsetting", redefines: "Redefinition",
        references: "ReferenceSubsetting", specializes: "Subclassification" };
      const specs = s.specializations.map((sp) => [kinds[sp.kind] ?? sp.kind, sp.targetId]);
      if (c.check === "specializations") return sortPairs(specs);
      return specs.filter(([k]) => ["Subsetting", "Redefinition", "ReferenceSubsetting"].includes(k)).map(([, t]) => t).sort(byString);
    }
    case "types":
      if (s.type === undefined) throw new Unsupported("no type info");
      // TypeFacts reports one resolved type
      return s.type.resolvedId === "" ? [] : [s.type.resolvedId];
    case "idRoundTrip": {
      const again = await lookup(m, s.id);
      return again !== undefined && again.id === s.id;
    }
    case "substates":
      return (await s.children()).filter((ch) => ch.kind === "stateUsage").map((ch) => ch.name).sort(byString);
    case "directGenerals":
      return s.specializations.filter((sp) => sp.kind === "specializes").map((sp) => sp.targetId).sort(byString);
    case "ownedFeatureNames": case "inheritedFeatureNames": case "redefinitions": {
      const children = (await s.children()).filter((ch) => !ch.kind.toLowerCase().endsWith("def"));
      const owned = children.map((ch) => ch.name);
      if (c.check === "ownedFeatureNames") return owned.sort(byString);
      if (c.check === "redefinitions") {
        return sortPairs(children.flatMap((ch) => ch.specializations.filter((sp) => sp.kind === "redefines").map((sp) => [ch.id, sp.targetId])));
      }
      // members the Symbol lists that it does not own: attribute facts not among the children
      return s.attributes.map((a) => a.name).filter((n) => !owned.includes(n)).sort(byString);
    }
    case "metadataDefs": case "metadataValue": {
      // annotations an element lists: its metadata-usage children
      const annotations = (await s.children()).filter((ch) => ch.kind === "metadataUsage");
      if (c.check === "metadataValue") {
        if (annotations.length === 0) return `<no annotation of ${s.id} readable as a Symbol>`;
        return toJson(annotations[0].attribute("severity")?.value);
      }
      return [...new Set(annotations.map((a) => a.type?.resolvedId ?? "").filter((t) => t !== ""))].sort(byString);
    }
    case "kind":
      return metaclassOf(s.kind);
    // Symbol metadata carries `abstract` / `variation: true` when they hold, nothing otherwise
    case "isAbstract":
      return s.metadata.abstract === "true";
    case "isVariation":
      return s.metadata.variation === "true";
    case "referenceTarget":
      if (c.via === "type") return s.type && s.type.resolvedId !== "" ? s.type.resolvedId : null;
      return s.specializations.find((sp) => sp.kind === "subsets")?.targetId ?? null;
    case "parameters":
      // children the Symbol lists that carry a direction in their metadata
      return sortPairs((await s.children()).filter((ch) => (ch.metadata.direction ?? "") !== "").map((ch) => [ch.metadata.direction, ch.name]));
    case "variants":
      // variant usages carry `variant: true` in their metadata
      return (await s.children()).filter((ch) => ch.metadata.variant === "true").map((ch) => ch.name).sort(byString);
    case "typeIsConjugated": {
      if (s.type === undefined || s.type.resolvedId === "") return null;
      // a conjugated port definition is named "~" + its original's name (SysML spec)
      return (await sym(m, s.type.resolvedId)).name.startsWith("~");
    }
    case "direction":
      // the member's direction as the Symbol reports it when listed through the port
      return s.metadata.direction ?? null;
    case "endCount": case "endNames": case "endReferences": {
      if (s.kind.toLowerCase().endsWith("def") || s.kind.endsWith("Definition")) {
        throw new Unsupported("the Symbol API does not mark the end features of a definition");
      }
      const ends = (await s.children()).filter((ch) => ch.kind.toLowerCase() === "connectorend");
      if (c.check === "endCount") return ends.length;
      if (c.check === "endNames") return ends.map((e) => e.name);
      // an end's reference is reported, if at all, as a subsets/references specialization
      return ends.map((e) => e.specializations.filter((sp) => sp.kind === "subsets" || sp.kind === "references").map((sp) => sp.targetId));
    }
    case "multiplicity": {
      if (s.multiplicity === undefined) return null;
      const { lower, upper } = s.multiplicity;
      return `${lower !== "" ? lower : upper === "*" ? "0" : upper}..${upper}`;
    }
    case "value": {
      // a feature's value is reported in its owner's attribute facts
      const o = await sym(m, owner);
      const fact = o.attribute(s.name);
      return fact === undefined ? `<${s.name} not in attributes of ${owner}>` : toJson(fact.value);
    }
  }
  throw new Error(`unknown check ${c.check}`);
}

/** Equal as JSON values; numbers by value. */
function matches(got: Json, want: Json): boolean {
  if (Array.isArray(got) && Array.isArray(want)) {
    return got.length === want.length && got.every((g, i) => matches(g, want[i]));
  }
  return got === want;
}

/** Parse a model; one the MDK reports errors for makes every case that uses it an error. */
async function load(conn: Connection, file: string): Promise<Model | string> {
  let model: Model;
  try {
    model = await conn.loads(readFileSync(join(DATA, file), "utf8"));
  } catch (error) {
    return `model not parsed: ${error}`;
  }
  const errors = model.errors.slice(0, 2).map((d) => `line ${d.startLine ?? 0}: ${d.message}`);
  return errors.length > 0 ? `model rejected: ${errors.join("; ")}` : model;
}

async function open(): Promise<Connection> {
  if (BACKEND === "wasm") {
    // the locally built module and the Go runtime it was built with, never a package's
    const dir = process.env.OPENSYSML_WASM_DIR || join(OPENSYSML, "bin", "wasm", "release");
    return connectWasm({ wasm: join(dir, "sysml-wasm.wasm"), wasmExec: join(dir, "wasm_exec.js") });
  }
  // the service binary is the locally built one, never a downloaded release
  process.env.OPENSYSML_BINARY ||= join(OPENSYSML, "bin", "sysml-grpc");
  return connect();
}

const conn = await open();
const rows: string[][] = [];
let failed = 0;
const models = new Map<string, Model | string>();
for (const file of readdirSync(join(DATA, "cases")).filter((f) => f.endsWith(".json")).sort()) {
  const spec = JSON.parse(readFileSync(join(DATA, "cases", file), "utf8"));
  for (const c of spec.cases as Case[]) {
    const modelFile: string = c.model ?? spec.model;
    if (!models.has(modelFile)) {
      models.set(modelFile, await load(conn, modelFile));
    }
    const model = models.get(modelFile)!;
    let outcome: string;
    let detail = "";
    if (typeof model === "string") {
      outcome = "error";
      detail = model;
    } else {
      try {
        let got: Json;
        try {
          got = await check(model, c);
        } catch (stop) {
          if (!(stop instanceof Answer)) throw stop;
          got = stop.value;
        }
        if (matches(got, c.expect) || (c.accept ?? []).some((a) => matches(got, a))) {
          outcome = "pass";
        } else {
          outcome = "fail";
          detail = `${c.check} ${c.element}: got ${JSON.stringify(got)}, want ${JSON.stringify(c.expect)}`;
        }
      } catch (stop) {
        if (stop instanceof Unsupported) {
          outcome = "unsupported";
          detail = stop.why;
        } else {
          outcome = "error";
          detail = String(stop);
        }
      }
    }
    detail = detail.replace(/\s+/g, " ");
    console.log(`${c.id} ${outcome} ${detail}`);
    if (outcome === "fail" || outcome === "error") failed++;
    rows.push([SUITE, spec.matrix, c.id, outcome, detail]);
  }
}
await conn.close();

const out = resolvePath(process.env.RESULTS_DIR || join(HERE, "..", "results"));
mkdirSync(out, { recursive: true });
const q = (s: string): string => `"${s.replaceAll('"', '""')}"`;
writeFileSync(join(out, `${SUITE}.csv`),
  ["suite,matrix,id,outcome,detail", ...rows.map((r) => r.map(q).join(","))].join("\n") + "\n");
console.log(`${SUITE}: ${rows.length} cases, ${failed} failed or errored`);
process.exitCode = failed > 0 ? 1 : 0;
