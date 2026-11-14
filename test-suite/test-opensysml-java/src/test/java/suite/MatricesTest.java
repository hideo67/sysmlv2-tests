package suite;

import static org.junit.jupiter.api.Assertions.*;
import static org.junit.jupiter.api.Assumptions.abort;

import com.google.gson.*;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.stream.*;
import org.junit.jupiter.api.*;
import org.openmbee.opensysml.*;

/**
 * Every matrix in data/cases/*.json against the OpenSysML Java client (client/java), over
 * the locally built sysml-grpc.
 *
 * <p>Only the Symbol API is used: it is OpenSysML's element API, the counterpart of the
 * Pilot's EMF model and sysml-toolkit's ResolvedModel (DISCUSSIONS.md, Step 5 decision). When
 * the Symbol API has no field for a read, the result is unsupported, and the detail says
 * whether the standard SysML v2 API &amp; Services query API offers the property; the query API
 * is consulted for that note only, never for a value.
 *
 * <p>A Java Symbol has the shape of the TypeScript client's ModelSymbol (child ids and the
 * attribute facts the service sends, no member enumeration), so the reads follow the
 * TypeScript adapter (test-opensysml-ts/matrices.ts).
 */
class MatricesTest {
    static final String SUITE = "opensysml-java";
    static Connection connection;
    static final List<JsonObject> specs = new ArrayList<>();
    static final Map<String, Model> models = new HashMap<>();
    /** Model files the MDK reported errors for: every case using them is an error. */
    static final Map<String, String> rejected = new HashMap<>();
    static final List<String[]> rows = new ArrayList<>();
    static final Map<String, Object> instantiations = new HashMap<>();

    /** An early answer of a check: the value the case compares. */
    static final class Answer extends RuntimeException {
        final Object value;
        Answer(Object value) {
            super(null, null, false, false);
            this.value = value;
        }
    }

    @BeforeAll
    static void load() throws Exception {
        Path opensysml = Path.of(System.getProperty("opensysmlDir"));
        requireLocalClient(opensysml);
        Path data = Path.of(System.getProperty("dataDir"));
        // the service binary is the locally built one, never a downloaded release
        connection = Connection.open(ConnectionOptions.builder()
            .binaryPath(opensysml.resolve("bin").resolve("sysml-grpc")).build());
        try (Stream<Path> files = Files.list(data.resolve("cases"))) {
            for (Path f : files.filter(p -> p.toString().endsWith(".json")).sorted().toList()) {
                JsonObject spec = JsonParser.parseString(Files.readString(f)).getAsJsonObject();
                LinkedHashSet<String> files2 = new LinkedHashSet<>(List.of(spec.get("model").getAsString()));
                spec.getAsJsonArray("cases").forEach(c -> {
                    if (c.getAsJsonObject().has("model")) files2.add(c.getAsJsonObject().get("model").getAsString());
                });
                for (String file : files2) {
                    if (models.containsKey(file) || rejected.containsKey(file)) continue;
                    try {
                        Model m = connection.load(data.resolve(file));
                        List<String> errors = m.errors().stream().limit(2)
                            .map(d -> "line " + d.span().map(Diagnostic.Span::startLine).orElse(0) + ": " + d.message())
                            .toList();
                        if (!errors.isEmpty()) rejected.put(file, "model rejected: " + String.join("; ", errors));
                        else models.put(file, m);
                    } catch (OpenSysMLException e) {
                        rejected.put(file, "model not parsed: " + e.getMessage());
                    }
                }
                specs.add(spec);
            }
        }
    }

    /** The client jar on the class path must be the one built from the local checkout. */
    static void requireLocalClient(Path opensysml) throws Exception {
        String version = System.getProperty("opensysmlVersion");
        Path built = opensysml.resolve("client/java/opensysml-client/target/opensysml-" + version + ".jar");
        Path used = Path.of(Connection.class.getProtectionDomain().getCodeSource().getLocation().toURI());
        if (!Files.exists(built)) {
            fail("no local build of the Java client at " + built
                + "; run mvn -f OpenSysML/client/java/pom.xml install");
        }
        if (!Arrays.equals(sha256(built), sha256(used))) {
            fail("the Java client on the class path (" + used + ") is not the local build (" + built
                + "); run mvn -f OpenSysML/client/java/pom.xml install");
        }
    }

    static byte[] sha256(Path p) throws Exception {
        return MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(p));
    }

    @AfterAll
    static void finish() throws Exception {
        if (connection != null) connection.close();
        String dir = System.getProperty("resultsDir");
        Path out = dir == null || dir.isEmpty() || dir.startsWith("${") ? Path.of("..", "results") : Path.of(dir);
        Files.createDirectories(out);
        StringBuilder sb = new StringBuilder("suite,matrix,id,outcome,detail\n");
        for (String[] r : rows) {
            sb.append(Arrays.stream(r).map(s -> "\"" + s.replace("\"", "\"\"").replaceAll("\\s+", " ") + "\"")
                .collect(Collectors.joining(","))).append('\n');
        }
        Files.writeString(out.resolve(SUITE + ".csv"), sb.toString());
    }

    @TestFactory
    Stream<DynamicContainer> matrices() {
        return specs.stream().map(spec -> {
            String matrix = spec.get("matrix").getAsString();
            return DynamicContainer.dynamicContainer(matrix,
                StreamSupport.stream(spec.getAsJsonArray("cases").spliterator(), false)
                    .map(JsonElement::getAsJsonObject)
                    .map(c -> {
                        String file = c.has("model") ? c.get("model").getAsString() : spec.get("model").getAsString();
                        return DynamicTest.dynamicTest(c.get("id").getAsString(), () -> recorded(matrix, file, c));
                    }));
        });
    }

    static void recorded(String matrix, String file, JsonObject c) {
        String id = c.get("id").getAsString();
        if (rejected.containsKey(file)) {
            rows.add(new String[] {SUITE, matrix, id, "error", rejected.get(file)});
            fail(rejected.get(file));
        }
        try {
            Object actual;
            try {
                actual = check(models.get(file), c);
            } catch (Answer a) {
                actual = a.value;
            }
            JsonElement got = new Gson().toJsonTree(actual);
            boolean ok = same(got, c.get("expect"));
            if (!ok && c.has("accept")) {
                for (JsonElement a : c.getAsJsonArray("accept")) ok |= same(got, a);
            }
            if (!ok) fail(c.get("check").getAsString() + " " + c.get("element").getAsString()
                + ": got " + got + ", want " + c.get("expect"));
            rows.add(new String[] {SUITE, matrix, id, "pass", ""});
        } catch (org.opentest4j.TestAbortedException e) {
            String why = String.valueOf(e.getMessage()).replaceFirst("^Assumption failed: ", "").replaceFirst("^UNSUPPORTED: ", "");
            rows.add(new String[] {SUITE, matrix, id, "unsupported", why});
            throw e;
        } catch (AssertionError e) {
            rows.add(new String[] {SUITE, matrix, id, "fail", String.valueOf(e.getMessage())});
            throw e;
        } catch (RuntimeException e) {
            rows.add(new String[] {SUITE, matrix, id, "error", e.toString()});
            throw e;
        }
    }

    static boolean same(JsonElement got, JsonElement want) {
        if (got.isJsonPrimitive() && want.isJsonPrimitive()
                && got.getAsJsonPrimitive().isNumber() && want.getAsJsonPrimitive().isNumber()) {
            return got.getAsDouble() == want.getAsDouble();
        }
        if (got.isJsonArray() && want.isJsonArray()) {
            JsonArray g = got.getAsJsonArray(), w = want.getAsJsonArray();
            if (g.size() != w.size()) return false;
            for (int i = 0; i < g.size(); i++) if (!same(g.get(i), w.get(i))) return false;
            return true;
        }
        return got.equals(want);
    }

    // ---- helpers ------------------------------------------------------------------------

    /** Qualified names compared without quoting: OpenSysML spells `CmdPort::~CmdPort`. */
    static String norm(String qn) {
        return qn.replace("'", "");
    }

    static String parent(String qn) {
        int i = qn.lastIndexOf("::");
        return i < 0 ? "" : qn.substring(0, i);
    }

    static String last(String qn) {
        int i = qn.lastIndexOf("::");
        return i < 0 ? qn : qn.substring(i + 2);
    }

    static List<String> sorted(Stream<String> s) {
        return s.sorted().collect(Collectors.toCollection(ArrayList::new));
    }

    static List<List<String>> sortPairs(Stream<List<String>> s) {
        return s.sorted(Comparator.comparing(p -> String.join(" ", p))).collect(Collectors.toCollection(ArrayList::new));
    }

    /** The client's name lookup, Model.findSymbol(qualified name), as written or unquoted. */
    static Optional<Symbol> lookup(Model m, String qn) {
        for (String name : List.of(qn, norm(qn))) {
            Optional<Symbol> s = m.findSymbol(name);
            if (s.isPresent()) return s;
        }
        return Optional.empty();
    }

    static Symbol sym(Model m, String qn) {
        return lookup(m, qn).orElseThrow(() -> new Answer("<no symbol " + qn + ">"));
    }

    /** Ids of the members a Symbol enumerates (own and inherited, library-inherited ones
     * included), unquoted: Model.symbol with SymbolOptions.withLibraryMembers (DISCUSSIONS.md, Step 16). */
    static List<Symbol.Member> members(Model m, Symbol s) {
        return m.symbol(s.id(), SymbolOptions.defaults().withLibraryMembers(true)).members();
    }

    static List<String> memberIds(Model m, Symbol s) {
        return members(m, s).stream().map(mb -> norm(mb.id())).toList();
    }

    /** Symbol kinds that are not features (internal/semantic/symbols/symbol.go); every other kind,
     * the usages above all, is a feature. */
    static final Set<String> NON_FEATURE_KINDS = Set.of("documentation", "comment", "textualRepresentation", "alias",
        "dependency", "relationship", "namespace", "package", "kermlType", "metaclass");

    static boolean isFeatureKind(String kind) {
        return !NON_FEATURE_KINDS.contains(kind) && !kind.endsWith("Def");
    }

    /** Where a member declared in an element is looked for: the element's children, or, read through
     * a usage ({@code part holder : Holder;}), the usage's children and members, since what the usage
     * gets from its definition are inherited memberships (as the Python harness reads them). */
    static List<Symbol> scopeSymbols(Model m, Symbol o, boolean through) {
        if (!through) return children(m, o);
        List<Symbol> out = new ArrayList<>(children(m, o));
        for (String id : memberIds(m, o)) {
            if (out.stream().noneMatch(x -> norm(x.id()).equals(id))) lookup(m, id).ifPresent(out::add);
        }
        return out;
    }

    /** The symbols of a Symbol's child ids, each looked up by its id; one not found is left out. */
    static List<Symbol> children(Model m, Symbol s) {
        List<Symbol> out = new ArrayList<>();
        for (String id : s.childIds()) lookup(m, id).ifPresent(out::add);
        return out;
    }

    static String resolved(Symbol s) {
        return s.typeFacts().flatMap(Symbol.TypeFacts::resolvedId).orElse("");
    }

    static Optional<Symbol.Attribute> attribute(Symbol s, String name) {
        return s.attributes().stream().filter(a -> a.name().equals(name)).findFirst();
    }

    /** Symbol kinds spelled as the spec metaclass (`calcDef` -> `CalculationDefinition`). */
    static String metaclassOf(String kind) {
        if (kind.isEmpty()) return "";
        if (kind.equals("bindingUsage")) return "BindingConnectorAsUsage";
        for (String[] w : new String[][] {{"calc", "calculation"}, {"enum", "enumeration"}}) {
            String rest = kind.substring(Math.min(w[0].length(), kind.length()));
            if (kind.startsWith(w[0]) && !rest.isEmpty() && Character.isUpperCase(rest.charAt(0))) kind = w[1] + rest;
        }
        if (kind.endsWith("Def")) kind += "inition";
        return Character.toUpperCase(kind.charAt(0)) + kind.substring(1);
    }

    /** Unsupported: the Symbol API has no field for `what`; notes whether the query API offers `prop`. */
    static void noSymbolField(Model m, String element, String prop, String what) {
        String note = "the standard query API does not offer it either";
        try {
            List<QueryElement> rows = m.query(Query.all().withScope(List.of(element)).withSelect(List.of(prop)));
            if (rows.stream().anyMatch(r -> r.properties().containsKey(prop))) {
                note = "available through the standard query API (" + prop + ")";
            }
        } catch (OpenSysMLException e) {
            // not offered
        }
        abort("UNSUPPORTED: no Symbol field for " + what + "; " + note);
    }

    /** A scalar value as JSON; anything else as a text no expectation matches. */
    static Object toJson(Value v) {
        if (v == null) return null;
        return switch (v) {
            case Value.IntegerValue i -> i.value();
            case Value.BigIntegerValue b -> b.value();
            case Value.RealValue r -> r.value();
            case Value.RationalValue r -> r.value().doubleValue();
            case Value.BooleanValue b -> b.value();
            case Value.StringValue s -> s.value();
            case Value.NullValue n -> null;
            case Value.UnsetValue u -> null;
            default -> "<" + v.getClass().getSimpleName() + ">";
        };
    }

    static Object magnitude(Quantity q) {
        Number n = q.magnitude();
        return n instanceof Rational r ? r.doubleValue() : n;
    }

    /** E10: the feature's value from the evaluation API, in its part def's scope or with the usage as subject. */
    static Object evaluate(Model m, JsonObject c, String check, String element) {
        Value v;
        try {
            v = c.has("subject") ? m.evalWithSubject(last(element), c.get("subject").getAsString())
                : m.evalInContext(last(element), parent(element));
        } catch (OpenSysMLException e) {
            return "<evaluation failed: " + e.getMessage() + ">";
        }
        if (check.equals("evaluatedUnit")) {
            return v instanceof Value.QuantityValue q ? q.quantity().unit().orElse(null) : null;
        }
        return v instanceof Value.QuantityValue q ? magnitude(q.quantity()) : toJson(v);
    }

    /** What a path of feature names reaches in an instantiated object tree. */
    sealed interface Node permits Obj, Scalar, ListNode, Missing {}
    record Obj(Instance obj) implements Node {}
    record Scalar(Value value) implements Node {}
    record ListNode(List<Node> items) implements Node {}
    record Missing(String why) implements Node {}

    static Node walk(Instantiation tree, String path) {
        java.util.function.Function<Value, Node> resolve = v -> {
            if (v instanceof Value.InstanceReference ref) {
                Optional<Instance> o = tree.resolve(ref);
                if (o.isPresent()) return new Obj(o.get());
            }
            return new Scalar(v);
        };
        Node cur = new Obj(tree.root());
        for (String name : path.split("\\.")) {
            if (!(cur instanceof Obj o)) return new Missing("<" + name + ": not an object>");
            Instance.FeatureValue fv = o.obj().featureValues().get(name);
            if (fv == null) return new Missing("<no feature " + name + ">");
            if (fv.error().isPresent()) return new Missing("<feature " + name + ": " + fv.error().get() + ">");
            cur = fv.value().isPresent() ? resolve.apply(fv.value().get())
                : new ListNode(fv.values().stream().map(resolve).toList());
        }
        return cur;
    }

    static String describe(Node n) {
        return switch (n) {
            case Obj o -> "<object " + o.obj().typeSymbolId() + ">";
            case Scalar s -> "<" + s.value().getClass().getSimpleName() + ">";
            case ListNode l -> "<list of " + l.items().size() + ">";
            case Missing x -> x.why();
        };
    }

    /** F10: walk `path` from the object Model.instantiate(root) builds. */
    static Object instanceCheck(Model m, JsonObject c, String check, String element) {
        Object tree = instantiations.computeIfAbsent(m.hash() + " " + element, k -> {
            try {
                return m.instantiate(element);
            } catch (OpenSysMLException e) {
                return "<instantiation failed: " + e.getMessage() + ">";
            }
        });
        if (tree instanceof String s) return s;
        Instantiation t = (Instantiation) tree;
        Node target = walk(t, c.has("path") ? c.get("path").getAsString() : "");
        switch (check) {
            case "ownerPath": {
                // the object's path through its owners: of every path InstancePaths lists, the
                // first that steps through no connector end (an end reaches the object it
                // references, not one it owns)
                if (!(target instanceof Obj o)) return describe(target);
                InstancePaths paths;
                try {
                    paths = m.instancePaths(o.obj());
                } catch (OpenSysMLException e) {
                    return "<InstancePaths failed: " + e.getMessage() + ">";
                }
                for (InstancePaths.Path p : paths.paths()) {
                    boolean throughEnd = p.steps().stream().anyMatch(st -> lookup(m, st.featureSymbolId())
                        .map(f -> f.kind().equals("connectorEnd")).orElse(false));
                    if (!throughEnd) return p.path();
                }
                return "<no path to " + c.get("path").getAsString() + " through owners only>";
            }
            case "instanceType":
                return target instanceof Obj o ? o.obj().typeSymbolId() : describe(target);
            case "instanceValue":
                return target instanceof Scalar s ? toJson(s.value()) : describe(target);
            case "instanceCount":
                return target instanceof ListNode l ? l.items().size() : target instanceof Obj ? 1 : 0;
            default:
                Node other = walk(t, c.has("path2") ? c.get("path2").getAsString() : "");
                return target instanceof Obj a && other instanceof Obj b && a.obj().id() == b.obj().id();
        }
    }

    // ---- the reads ----------------------------------------------------------------------

    static Object check(Model m, JsonObject c) {
        String check = c.get("check").getAsString();
        String element = c.get("element").getAsString();
        List<String> through = new ArrayList<>();
        if (c.has("through")) {
            JsonElement t = c.get("through");
            if (t.isJsonArray()) t.getAsJsonArray().forEach(x -> through.add(x.getAsString()));
            else through.add(t.getAsString());
        }
        JsonObject unnamed = c.has("unnamed") ? c.getAsJsonObject("unnamed") : null;

        switch (check) {
            case "instanceType", "instanceValue", "instanceCount", "endIdentity", "ownerPath":
                return instanceCheck(m, c, check, element);
            case "evaluatedValue", "evaluatedUnit":
                return evaluate(m, c, check, element);
            case "resolve":
                // the client's name lookup: Model.findSymbol(qualified name)
                return lookup(m, element).map(Symbol::id).orElse(null);
            case "entryKind", "doKind", "exitKind", "isParallel", "source", "target", "triggerPayload",
                 "guardKind", "effectKind": {
                String prop = Map.of("entryKind", "entryAction", "doKind", "doAction", "exitKind", "exitAction",
                    "triggerPayload", "triggerAction", "guardKind", "guardExpression", "effectKind", "effectAction")
                    .getOrDefault(check, check);
                noSymbolField(m, element, prop, prop);
            }
            case "payloadTypes", "sourceOutput", "targetInput": {
                String prop = Map.of("payloadTypes", "payloadType", "sourceOutput", "sourceOutputFeature",
                    "targetInput", "targetInputFeature").get(check);
                noSymbolField(m, element, prop, "the flow's " + prop);
            }
            // reads the Symbol API has no field for: unsupported, before the element is even
            // looked up (unsupported takes precedence over not being visible)
            case "shortName": noSymbolField(m, norm(element), "shortName", "the short name");
            case "owner": noSymbolField(m, norm(element), "owner", "the owner");
            case "isIndividual": noSymbolField(m, norm(element), "isIndividual", "isIndividual");
            case "result": noSymbolField(m, norm(element), "result", "the result parameter");
            case "subject": noSymbolField(m, norm(element), "subjectParameter", "the subject parameter");
            case "documentation", "comments", "textualRepresentation":
                noSymbolField(m, norm(element), check.equals("comments") ? "comment" : check, check);
            case "isComposite", "isReference":
                noSymbolField(m, element, check, check);
            case "sourceFeature", "targetFeature", "relatedFeature":
                if (unnamed != null) {
                    abort("UNSUPPORTED: no Symbol field for " + check + "; the query API cannot address an unnamed element");
                }
                noSymbolField(m, element, check, check);
            case "allSupertypes":
                abort("UNSUPPORTED: neither the Symbol nor the query API gives the closure of supertypes");
            case "annotatedElement":
                abort("UNSUPPORTED: neither the Symbol nor the query API reports what a metadata usage annotates");
            case "payloadArgument", "senderArgument", "receiverArgument", "assignedFeature":
                abort("UNSUPPORTED: the Symbol API reports no arguments of an action");
            case "valueKind", "valueOperator", "valueReferences", "valueText":
                abort("UNSUPPORTED: the Symbol API reports a value only as a folded constant, with no expression structure or text");
            case "exprKind", "instantiatedType", "argumentCount", "argumentReferences", "hasResult", "resultType":
                abort("UNSUPPORTED: the Symbol API reports neither the arguments of an action nor expression structure, "
                    + "so no constructor expression is reachable");
            case "isDefault":
                abort("UNSUPPORTED: neither Symbol nor its attribute facts tell a default from a bound value");
            case "unnamedPartCount": {
                // unnamed part usages declared in the element, among the children the Symbol lists
                Symbol o = sym(m, norm(through.isEmpty() ? element : through.get(through.size() - 1)));
                String prefix = norm(element) + "::";
                return scopeSymbols(m, o, !through.isEmpty()).stream()
                    .filter(ch -> ch.name().isEmpty() && ch.kind().equals("partUsage") && norm(ch.id()).startsWith(prefix)).count();
            }
            default:
                break;
        }

        String owner = parent(element);
        String id = norm(element);
        if (!through.isEmpty()) {
            // each step is read as a member the previous Symbol lists: as a child, in its
            // members (own and inherited), or (for attributes, own and inherited) in its attribute facts
            Symbol cur = sym(m, norm(through.get(0)));
            List<String> steps = new ArrayList<>(through.subList(1, through.size()));
            if (unnamed == null) steps.add(element);
            for (String raw : steps) {
                String step = norm(raw);
                boolean visible = cur.childIds().contains(step) || attribute(cur, last(step)).isPresent()
                    || memberIds(m, cur).contains(step);
                if (!visible) return "<" + step + " not visible through " + cur.id() + ">";
                owner = cur.id();
                cur = sym(m, step);
            }
        }
        if (unnamed != null) {
            // the index-th unnamed member of the metaclass declared in the element
            Symbol o = sym(m, norm(through.isEmpty() ? element : through.get(through.size() - 1)));
            String meta = unnamed.get("metaclass").getAsString().toLowerCase(Locale.ROOT);
            int index = unnamed.get("index").getAsInt();
            String prefix = norm(element) + "::";
            List<Symbol> found = scopeSymbols(m, o, !through.isEmpty()).stream()
                .filter(ch -> ch.name().isEmpty() && ch.kind().toLowerCase(Locale.ROOT).contains(meta)
                    && (through.isEmpty() || norm(ch.id()).startsWith(prefix))).toList();
            if (found.size() <= index) {
                return "<unnamed " + unnamed.get("metaclass").getAsString() + " #" + index + " of " + element + " not listed>";
            }
            id = found.get(index).id();
        }
        Symbol s = sym(m, id);

        switch (check) {
            case "name":
                return s.name();
            case "type":
                if (s.typeFacts().isEmpty()) abort("UNSUPPORTED: no type info");
                // the derived Feature::type, most specific first (resolvedId is the typing as written)
                return s.typeFacts().get().types().stream().findFirst().map(Symbol.TypeRef::id).orElse("");
            case "specializations", "subsettedFeatures": {
                // OpenSysML's Specialization kind spelled as the spec metaclass
                Map<String, String> kinds = Map.of("typing", "FeatureTyping", "subsets", "Subsetting",
                    "redefines", "Redefinition", "references", "ReferenceSubsetting", "specializes", "Subclassification");
                List<List<String>> specs = s.specializations().stream()
                    .map(sp -> Arrays.asList(kinds.getOrDefault(sp.kind(), sp.kind()), sp.targetId().orElse(""))).toList();
                if (check.equals("specializations")) return sortPairs(specs.stream());
                return sorted(specs.stream().filter(p -> List.of("Subsetting", "Redefinition", "ReferenceSubsetting")
                    .contains(p.get(0))).map(p -> p.get(1)));
            }
            case "types": {
                if (s.typeFacts().isEmpty()) abort("UNSUPPORTED: no type info");
                // the derived Feature::type (resolvedId is the typing as written)
                return sorted(s.typeFacts().get().types().stream().map(Symbol.TypeRef::id));
            }
            case "idRoundTrip":
                return lookup(m, s.id()).map(again -> again.id().equals(s.id())).orElse(false);
            case "substates":
                return sorted(children(m, s).stream().filter(ch -> ch.kind().equals("stateUsage")).map(Symbol::name));
            case "directGenerals":
                return sorted(s.specializations().stream().filter(sp -> sp.kind().equals("specializes"))
                    .map(sp -> sp.targetId().orElse("")));
            case "ownedFeatureNames", "inheritedFeatureNames", "redefinitions": {
                List<Symbol> kids = children(m, s).stream()
                    .filter(ch -> !ch.kind().toLowerCase(Locale.ROOT).endsWith("def")).toList();
                List<String> owned = kids.stream().map(Symbol::name).toList();
                if (check.equals("ownedFeatureNames")) return sorted(owned.stream());
                if (check.equals("redefinitions")) {
                    return sortPairs(kids.stream().flatMap(ch -> ch.specializations().stream()
                        .filter(sp -> sp.kind().equals("redefines"))
                        .map(sp -> List.of(ch.id(), sp.targetId().orElse("")))));
                }
                // members the Symbol lists that it does not own: inherited members, and attribute
                // facts (own and inherited) not among the children
                // features only: Type::inheritedFeature, not inheritedMembership (a doc or comment is not);
                // one entry per member id, since unnamed members all have the name ""
                Map<String, String> byId = new LinkedHashMap<>();
                members(m, s).stream().filter(mb -> mb.inherited() && isFeatureKind(mb.kind()))
                    .forEach(mb -> byId.putIfAbsent(mb.id(), mb.name()));
                List<String> inherited = new ArrayList<>(byId.values());
                for (Symbol.Attribute a : s.attributes()) {
                    if (!owned.contains(a.name()) && !inherited.contains(a.name())) inherited.add(a.name());
                }
                return sorted(inherited.stream());
            }
            case "metadataDefs", "metadataValue": {
                // annotations an element lists: its metadata-usage children
                List<Symbol> annotations = children(m, s).stream().filter(ch -> ch.kind().equals("metadataUsage")).toList();
                if (check.equals("metadataValue")) {
                    if (annotations.isEmpty()) return "<no annotation of " + s.id() + " readable as a Symbol>";
                    return attribute(annotations.get(0), "severity").flatMap(Symbol.Attribute::value)
                        .map(MatricesTest::toJson).orElse(null);
                }
                return sorted(annotations.stream().map(MatricesTest::resolved).filter(t -> !t.isEmpty()).distinct());
            }
            case "kind":
                return metaclassOf(s.kind());
            // Symbol metadata carries `abstract` / `variation: true` when they hold, nothing otherwise
            case "isAbstract":
                return "true".equals(s.metadata().get("abstract"));
            case "isVariation":
                return "true".equals(s.metadata().get("variation"));
            case "referenceTarget":
                if ("type".equals(c.has("via") ? c.get("via").getAsString() : null)) {
                    return resolved(s).isEmpty() ? null : resolved(s);
                }
                return s.specializations().stream().filter(sp -> sp.kind().equals("subsets"))
                    .map(sp -> sp.targetId().orElse(null)).findFirst().orElse(null);
            case "parameters":
                // members the Symbol lists (children and members, own and inherited) that carry a
                // direction in their metadata
                Set<String> ids = new LinkedHashSet<>(s.childIds());
                ids.addAll(memberIds(m, s));
                return sortPairs(ids.stream().map(x -> lookup(m, x)).flatMap(Optional::stream)
                    .filter(ch -> !ch.metadata().getOrDefault("direction", "").isEmpty())
                    .map(ch -> List.of(ch.metadata().get("direction"), ch.name())));
            case "variants":
                // variant usages carry `variant: true` in their metadata
                return sorted(children(m, s).stream().filter(ch -> "true".equals(ch.metadata().get("variant"))).map(Symbol::name));
            case "typeIsConjugated":
                if (resolved(s).isEmpty()) return null;
                // a conjugated port definition is named "~" + its original's name (SysML spec)
                return sym(m, resolved(s)).name().startsWith("~");
            case "direction":
                // the member's direction as the Symbol reports it when listed through the port
                return s.metadata().get("direction");
            case "endCount", "endNames", "endReferences": {
                if (s.kind().toLowerCase(Locale.ROOT).endsWith("def") || s.kind().endsWith("Definition")) {
                    abort("UNSUPPORTED: the Symbol API does not mark the end features of a definition");
                }
                List<Symbol> ends = children(m, s).stream()
                    .filter(ch -> ch.kind().equalsIgnoreCase("connectorEnd")).toList();
                if (check.equals("endCount")) return ends.size();
                if (check.equals("endNames")) return ends.stream().map(Symbol::name).toList();
                // an end's reference is reported, if at all, as a subsets/references specialization
                return ends.stream().map(e -> e.specializations().stream()
                    .filter(sp -> sp.kind().equals("subsets") || sp.kind().equals("references"))
                    .map(sp -> sp.targetId().orElse("")).toList()).toList();
            }
            case "multiplicity": {
                if (s.multiplicity().isEmpty()) return null;
                String lower = s.multiplicity().get().lower().orElse("");
                String upper = s.multiplicity().get().upper().orElse("");
                return (!lower.isEmpty() ? lower : upper.equals("*") ? "0" : upper) + ".." + upper;
            }
            case "value": {
                // a feature's value is reported in its owner's attribute facts
                Symbol o = sym(m, owner);
                Optional<Symbol.Attribute> fact = attribute(o, s.name());
                if (fact.isEmpty()) return "<" + s.name() + " not in attributes of " + owner + ">";
                return fact.get().value().map(MatricesTest::toJson).orElse(null);
            }
            default:
                throw new IllegalStateException("unknown check " + check);
        }
    }
}
