package suite;

import static org.junit.jupiter.api.Assertions.*;
import static org.junit.jupiter.api.Assumptions.abort;

import com.google.gson.*;
import java.nio.file.*;
import java.util.*;
import java.util.stream.*;
import org.eclipse.emf.ecore.EObject;
import org.eclipse.emf.ecore.resource.Resource;
import org.junit.jupiter.api.*;
import org.omg.sysml.interactive.SysMLInteractive;
import org.omg.sysml.lang.sysml.*;
import org.omg.sysml.util.ElementUtil;

/**
 * Every matrix in data/cases/*.json against the Pilot Implementation's EMF model
 * (org.omg.sysml.lang.sysml), the main API of the Pilot (DISCUSSIONS.md, Step 3).
 */
class MatricesTest {
    static SysMLInteractive interactive;
    static final List<JsonObject> specs = new ArrayList<>();
    static final Map<String, Resource> resources = new HashMap<>();
    static final List<String[]> rows = new ArrayList<>();
    /** Model files the Pilot reported errors for: every case using them is an error. */
    static final Map<String, String> rejected = new HashMap<>();

    @BeforeAll
    static void load() throws Exception {
        Path data = Path.of(System.getProperty("dataDir"));
        interactive = SysMLInteractive.createInstance();
        interactive.setVerbose(false);
        interactive.loadLibrary(Path.of(System.getProperty("libraryPath")).toAbsolutePath().toString());
        try (Stream<Path> files = Files.list(data.resolve("cases"))) {
            for (Path f : files.filter(p -> p.toString().endsWith(".json")).sorted().toList()) {
                JsonObject spec = JsonParser.parseString(Files.readString(f)).getAsJsonObject();
                // the matrix's model, and any model a case names for itself
                LinkedHashSet<String> models = new LinkedHashSet<>(List.of(spec.get("model").getAsString()));
                spec.getAsJsonArray("cases").forEach(c -> {
                    if (c.getAsJsonObject().has("model")) models.add(c.getAsJsonObject().get("model").getAsString());
                });
                for (String model : models) {
                    if (resources.containsKey(model)) continue;
                    interactive.setResource(Path.of(model).getFileName().toString());
                    interactive.parse(Files.readString(data.resolve(model)));
                    List<String> errors = interactive.validate().stream()
                        .filter(i -> i.getSeverity() == org.eclipse.xtext.diagnostics.Severity.ERROR)
                        .map(i -> "line " + i.getLineNumber() + ": " + i.getMessage()).limit(2).toList();
                    if (!errors.isEmpty()) rejected.put(model, "model rejected: " + String.join("; ", errors));
                    ElementUtil.transformAll(interactive.getResource(), true);
                    resources.put(model, interactive.getResource());
                }
                specs.add(spec);
            }
        }
    }

    @TestFactory
    Stream<DynamicContainer> matrices() {
        return specs.stream().map(spec -> {
            String matrix = spec.get("matrix").getAsString();
            return DynamicContainer.dynamicContainer(matrix,
                StreamSupport.stream(spec.getAsJsonArray("cases").spliterator(), false)
                    .map(JsonElement::getAsJsonObject)
                    .map(c -> {
                        String model = c.has("model") ? c.get("model").getAsString() : spec.get("model").getAsString();
                        return DynamicTest.dynamicTest(c.get("id").getAsString(),
                            () -> recorded(matrix, model, resources.get(model), c));
                    }));
        });
    }

    static void recorded(String matrix, String model, Resource resource, JsonObject c) {
        String id = c.get("id").getAsString();
        if (rejected.containsKey(model)) {
            rows.add(new String[] {"pilot-java", matrix, id, "error", rejected.get(model)});
            fail(rejected.get(model));
        }
        try {
            Object actual = check(resource, c);
            JsonElement got = new Gson().toJsonTree(actual);
            boolean ok = same(got, c.get("expect"));
            if (!ok && c.has("accept")) {
                for (JsonElement a : c.getAsJsonArray("accept")) ok |= same(got, a);
            }
            if (!ok) fail(c.get("check").getAsString() + " " + c.get("element").getAsString()
                + ": got " + got + ", want " + c.get("expect"));
            rows.add(new String[] {"pilot-java", matrix, id, "pass", ""});
        } catch (org.opentest4j.TestAbortedException e) {
            String why = String.valueOf(e.getMessage()).replaceFirst("^Assumption failed: ", "").replaceFirst("^UNSUPPORTED: ", "");
            rows.add(new String[] {"pilot-java", matrix, id, "unsupported", why});
            throw e;
        } catch (AssertionError e) {
            rows.add(new String[] {"pilot-java", matrix, id, "fail", String.valueOf(e.getMessage())});
            throw e;
        } catch (RuntimeException e) {
            rows.add(new String[] {"pilot-java", matrix, id, "error", e.toString()});
            throw e;
        }
    }

    static boolean same(JsonElement got, JsonElement want) {
        if (got.isJsonPrimitive() && want.isJsonPrimitive()
                && got.getAsJsonPrimitive().isNumber() && want.getAsJsonPrimitive().isNumber()) {
            return got.getAsDouble() == want.getAsDouble();
        }
        return got.equals(want);
    }

    /** Qualified names compared without quoting (`CmdPort::'~CmdPort'` vs `CmdPort::~CmdPort`). */
    static String norm(String qn) {
        return qn == null ? null : qn.replace("'", "");
    }

    /** The element with that qualified name: in the matrix's own resource, else anywhere
     *  in the resource set (the standard library). */
    static Element find(Resource resource, String qn) {
        Element e = findIn(resource, qn);
        if (e != null || resource.getResourceSet() == null) return e;
        for (Resource r : resource.getResourceSet().getResources()) {
            if (r != resource && (e = findIn(r, qn)) != null) return e;
        }
        return null;
    }

    static Element findIn(Resource resource, String qn) {
        for (var it = resource.getAllContents(); it.hasNext();) {
            EObject o = it.next();
            if (o instanceof Element e && norm(qn).equals(norm(e.getQualifiedName()))) return e;
        }
        return null;
    }

    /** The case's `through`: absent, one qualified name, or a path. */
    static List<String> throughPath(JsonObject c) {
        if (!c.has("through")) return List.of();
        JsonElement t = c.get("through");
        if (t.isJsonPrimitive()) return List.of(t.getAsString());
        List<String> out = new ArrayList<>();
        t.getAsJsonArray().forEach(x -> out.add(x.getAsString()));
        return out;
    }

    /** Features a type lists, own and inherited: feature, ownedFeature, inheritedFeature. */
    static List<Feature> visibleFeatures(Type t) {
        LinkedHashSet<Feature> out = new LinkedHashSet<>(t.getFeature());
        out.addAll(t.getOwnedFeature());
        out.addAll(t.getInheritedFeature());
        return new ArrayList<>(out);
    }

    /** Everything visible in a type: its features, and the members of all its memberships,
     *  inherited ones included (Namespace::member), such as a body annotation `@M;`. */
    static List<Element> visibleMembers(Type t) {
        LinkedHashSet<Element> out = new LinkedHashSet<>(visibleFeatures(t));
        out.addAll(t.getMember());
        return new ArrayList<>(out);
    }

    static Object literal(Expression e) {
        if (e == null) return null;
        if (e instanceof LiteralInfinity) return "*";
        if (e instanceof LiteralInteger i) return i.getValue();
        if (e instanceof LiteralRational r) return r.getValue();
        if (e instanceof LiteralBoolean b) return b.isValue();
        if (e instanceof LiteralString s) return s.getValue();
        return "<" + e.eClass().getName() + ">";
    }

    /** A referenced feature in chain form: chainingFeatures' qualified names, or [qn]. */
    static List<String> chainForm(Feature f) {
        if (f == null) return null;
        List<Feature> chain = f.getChainingFeature();
        return (chain.isEmpty() ? List.of(f) : chain).stream().map(Element::getQualifiedName).toList();
    }

    /** The value expression of the feature's owned FeatureValue membership. */
    static Expression valueExpr(Element e) {
        return e.getOwnedRelationship().stream().filter(r -> r instanceof FeatureValue)
            .map(r -> ((FeatureValue) r).getValue()).findFirst().orElse(null);
    }

    /** Referenced features of an expression, left to right, each in chain form. */
    static List<List<String>> references(Expression x) {
        List<List<String>> out = new ArrayList<>();
        if (x instanceof FeatureReferenceExpression r) {
            if (r.getReferent() != null) out.add(chainForm(r.getReferent()));
        } else if (x instanceof FeatureChainExpression fc) {
            List<String> chain = new ArrayList<>();
            if (!fc.getArgument().isEmpty()) {
                List<List<String>> src = references(fc.getArgument().get(0));
                if (!src.isEmpty()) chain.addAll(src.get(src.size() - 1));
            }
            if (fc.getTargetFeature() != null) chain.addAll(chainForm(fc.getTargetFeature()));
            out.add(chain);
        } else if (x instanceof InvocationExpression inv) {
            for (Expression a : inv.getArgument()) out.addAll(references(a));
        }
        return out;
    }

    /** MetadataUsages whose annotatedElement includes e, wherever they are owned. */
    static List<MetadataUsage> annotations(Resource resource, Element e) {
        List<MetadataUsage> out = new ArrayList<>();
        for (var it = resource.getAllContents(); it.hasNext();) {
            if (it.next() instanceof MetadataUsage mu && mu.getAnnotatedElement().contains(e)) out.add(mu);
        }
        return out;
    }

    static Object check(Resource resource, JsonObject c) {
        String check = c.get("check").getAsString();
        String qn = c.get("element").getAsString();
        List<String> path = throughPath(c);
        String through = path.isEmpty() ? null : path.get(0);

        if (check.equals("resolve")) {
            // KerML Namespace::resolve of the rest of the path, invoked on the matrix's root
            // package (resolution from the global namespace finds no user package in the Pilot)
            String[] parts = qn.split("::", 2);
            Membership mm = ((Namespace) find(resource, parts[0])).resolve(parts[1]);
            return mm == null || mm.getMemberElement() == null ? null : mm.getMemberElement().getQualifiedName();
        }
        if (check.equals("unnamedPartCount")) {
            Element scope = find(resource, through != null ? through : qn);
            Collection<? extends Element> members = through != null
                ? visibleFeatures((Type) scope) : ((Namespace) scope).getOwnedMember();
            return members.stream().filter(m -> m instanceof PartUsage)
                .filter(m -> m.getName() == null || m.getName().isEmpty())
                .filter(m -> m.getOwningNamespace() != null && qn.equals(m.getOwningNamespace().getQualifiedName()))
                .count();
        }
        // the element, read through each step of the path as a member visible in the previous one
        Element e;
        Type owner = null;
        if (c.has("unnamed")) {
            // the index-th unnamed member of the metaclass declared in `element`
            JsonObject u = c.getAsJsonObject("unnamed");
            Collection<? extends Element> members;
            if (path.isEmpty()) {
                members = ((Namespace) find(resource, qn)).getOwnedMember();
            } else {
                Element cur = find(resource, path.get(0));
                for (String step : path.subList(1, path.size())) {
                    cur = visibleFeatures((Type) cur).stream()
                        .filter(f -> norm(step).equals(norm(f.getQualifiedName()))).findFirst().orElse(null);
                    if (cur == null) return "<" + step + " not visible>";
                }
                owner = (Type) cur;
                members = visibleMembers((Type) cur);
            }
            List<Element> found = members.stream()
                .filter(m -> (m.getName() == null || m.getName().isEmpty())
                    && m.eClass().getName().contains(u.get("metaclass").getAsString())
                    && m.getOwningNamespace() != null && qn.equals(m.getOwningNamespace().getQualifiedName()))
                .collect(Collectors.toList());
            int i = u.get("index").getAsInt();
            if (found.size() <= i) return "<unnamed " + u.get("metaclass").getAsString() + " of " + qn + " not listed>";
            e = found.get(i);
        } else if (path.isEmpty()) {
            e = find(resource, qn);
            if (e == null) abort("UNSUPPORTED: no element " + qn);
        } else {
            e = find(resource, path.get(0));
            List<String> steps = new ArrayList<>(path.subList(1, path.size()));
            steps.add(qn);
            for (String step : steps) {
                Type cur = (Type) e;
                Element next = visibleMembers(cur).stream()
                    .filter(f -> norm(step).equals(norm(f.getQualifiedName()))).findFirst().orElse(null);
                if (next == null) return "<" + step + " not visible through " + cur.getQualifiedName() + ">";
                owner = cur;
                e = next;
            }
        }
        switch (check) {
            case "name": return e.getName();
            case "type": {
                List<Type> types = ((Feature) e).getType();
                return types.isEmpty() ? null : types.get(0).getQualifiedName();
            }
            case "isComposite": return ((Feature) e).isComposite();
            case "kind": return e.eClass().getName();
            case "documentation":
                return e.getDocumentation().stream().map(d -> d.getBody().trim()).sorted().toList();
            case "comments": {
                // Comments (not Documentation) whose annotatedElement includes e, wherever owned
                List<String> out = new ArrayList<>();
                for (var it = resource.getAllContents(); it.hasNext();) {
                    if (it.next() instanceof Comment cm && !(cm instanceof Documentation) && cm.getAnnotatedElement().contains(e))
                        out.add(cm.getBody().trim());
                }
                return out.stream().sorted().toList();
            }
            case "textualRepresentation":
                return e.getTextualRepresentation().stream().map(r -> List.of(r.getLanguage(), r.getBody().trim()))
                    .sorted(Comparator.comparing(Object::toString)).toList();
            case "entryKind": { ActionUsage a = ((StateUsage) e).getEntryAction(); return a == null ? null : a.eClass().getName(); }
            case "doKind": { ActionUsage a = ((StateUsage) e).getDoAction(); return a == null ? null : a.eClass().getName(); }
            case "exitKind": { ActionUsage a = ((StateUsage) e).getExitAction(); return a == null ? null : a.eClass().getName(); }
            case "substates":
                return ((Type) e).getOwnedFeature().stream().filter(f -> f instanceof StateUsage)
                    .map(f -> f.getName() == null ? "" : f.getName()).sorted().toList();
            case "isParallel": return ((StateUsage) e).isParallel();
            case "source": { Feature s = ((TransitionUsage) e).getSource(); return s == null ? null : s.getQualifiedName(); }
            case "target": { Feature s = ((TransitionUsage) e).getTarget(); return s == null ? null : s.getQualifiedName(); }
            case "triggerPayload": {
                List<AcceptActionUsage> t = ((TransitionUsage) e).getTriggerAction();
                if (t.isEmpty() || t.get(0).getPayloadParameter() == null) return null;
                List<Type> types = t.get(0).getPayloadParameter().getType();
                return types.isEmpty() ? null : types.get(0).getQualifiedName();
            }
            case "guardKind": {
                List<Expression> g = ((TransitionUsage) e).getGuardExpression();
                return g.isEmpty() ? null : g.get(0).eClass().getName();
            }
            case "effectKind": {
                List<ActionUsage> a = ((TransitionUsage) e).getEffectAction();
                return a.isEmpty() ? null : a.get(0).eClass().getName();
            }
            case "payloadTypes":
                return ((Flow) e).getPayloadType().stream().map(Element::getQualifiedName).sorted().toList();
            case "sourceOutput":
            case "targetInput": {
                // the flow feature redefines the participant's feature it names
                Feature f = check.equals("sourceOutput") ? ((Flow) e).getSourceOutputFeature() : ((Flow) e).getTargetInputFeature();
                if (f == null || f.getOwnedRedefinition().isEmpty()) return null;
                return f.getOwnedRedefinition().get(0).getRedefinedFeature().getQualifiedName();
            }
            case "referenceTarget": {
                if (c.get("via").getAsString().equals("type")) {
                    List<Type> types = ((Feature) e).getType();
                    return types.isEmpty() ? null : types.get(0).getQualifiedName();
                }
                return ((Feature) e).getOwnedSubsetting().stream().filter(r -> !r.isImplied())
                    .map(r -> r.getSubsettedFeature().getQualifiedName()).findFirst().orElse(null);
            }
            case "specializations":
                return ((Type) e).getOwnedSpecialization().stream().filter(r -> !r.isImplied())
                    .map(r -> List.of(r.eClass().getName(), r.getGeneral().getQualifiedName()))
                    .sorted(Comparator.comparing(Object::toString)).toList();
            case "subsettedFeatures":
                return ((Feature) e).getOwnedSubsetting().stream().filter(r -> !r.isImplied())
                    .map(r -> r.getSubsettedFeature().getQualifiedName()).sorted().toList();
            case "types":
                return ((Feature) e).getType().stream().map(Element::getQualifiedName).sorted().toList();
            case "owner":
                return e.getOwningNamespace() == null ? null : e.getOwningNamespace().getQualifiedName();
            case "idRoundTrip": {
                // the EMF identifier of the element (its URI fragment) finds it again
                Resource r = e.eResource();
                return r != null && r.getEObject(r.getURIFragment(e)) == e;
            }
            case "directGenerals":
                return ((Classifier) e).getOwnedSubclassification().stream().filter(r -> !r.isImplied())
                    .map(r -> r.getSuperclassifier().getQualifiedName()).sorted().toList();
            case "allSupertypes":
                return ((Type) e).allSupertypes().stream().map(Element::getQualifiedName).sorted().toList();
            case "ownedFeatureNames":
                return ((Type) e).getOwnedFeature().stream().map(f -> f.getName() == null ? "" : f.getName()).sorted().toList();
            case "inheritedFeatureNames":
                return ((Type) e).getInheritedFeature().stream().map(f -> f.getName() == null ? "" : f.getName()).sorted().toList();
            case "redefinitions": {
                List<List<String>> out = new ArrayList<>();
                for (Feature f : ((Type) e).getOwnedFeature())
                    for (Redefinition r : f.getOwnedRedefinition())
                        out.add(List.of(f.getQualifiedName(), r.getRedefinedFeature().getQualifiedName()));
                out.sort(Comparator.comparing(Object::toString));
                return out;
            }
            case "shortName": return e.getShortName();
            case "isAbstract": return ((Type) e).isAbstract();
            case "isVariation": return ((Definition) e).isVariation();
            case "parameters": {
                Type t = (Type) e;
                return t.getDirectedFeature().stream()
                    .map(f -> List.of(String.valueOf(t.directionOf(f)), f.getName() == null ? "" : f.getName()))
                    .sorted(Comparator.comparing(Object::toString)).toList();
            }
            case "result": {
                Feature r = e instanceof Function f ? f.getResult() : null;
                return r == null ? null : r.getName();
            }
            case "subject": {
                Usage s = e instanceof RequirementDefinition r ? r.getSubjectParameter()
                    : e instanceof CaseDefinition cd ? cd.getSubjectParameter() : null;
                return s == null ? null : s.getName();
            }
            case "isIndividual": return ((OccurrenceDefinition) e).isIndividual();
            case "variants":
                return ((Definition) e).getVariant().stream().map(v -> v.getName() == null ? "" : v.getName()).sorted().toList();
            case "metadataDefs":
                return annotations(resource, e).stream().map(mu -> mu.getMetadataDefinition())
                    .map(d -> d == null ? null : d.getQualifiedName()).sorted().toList();
            case "metadataValue":
            case "annotatedElement": {
                List<MetadataUsage> found = annotations(resource, e);
                if (found.isEmpty()) return "<no annotation of " + qn + " found>";
                MetadataUsage mu = found.get(0);
                if (check.equals("annotatedElement"))
                    return mu.getAnnotatedElement().stream().map(Element::getQualifiedName).toList();
                return mu.getOwnedFeature().stream().filter(f -> "severity".equals(f.getName()))
                    .map(f -> literal(valueExpr(f))).filter(Objects::nonNull).findFirst().orElse(null);
            }
            case "payloadArgument": {
                Expression x = e instanceof SendActionUsage s ? s.getPayloadArgument()
                    : e instanceof AcceptActionUsage a ? a.getPayloadArgument() : null;
                return x == null ? null : references(x);
            }
            case "senderArgument": {
                Expression x = e instanceof SendActionUsage s ? s.getSenderArgument() : null;
                return x == null ? null : references(x);
            }
            case "receiverArgument": {
                Expression x = e instanceof SendActionUsage s ? s.getReceiverArgument()
                    : e instanceof AcceptActionUsage a ? a.getReceiverArgument() : null;
                return x == null ? null : references(x);
            }
            case "assignedFeature":
                return e instanceof AssignmentActionUsage a ? chainForm(a.getReferent()) : null;
            case "valueText": abort("UNSUPPORTED: the EMF model has no source text of an expression");
            case "valueKind": {
                Expression x = valueExpr(e);
                return x == null ? null : x.eClass().getName();
            }
            case "valueOperator": {
                Expression x = valueExpr(e);
                return x instanceof OperatorExpression o ? o.getOperator() : null;
            }
            case "valueReferences": {
                Expression x = valueExpr(e);
                return x == null ? null : references(x);
            }
            case "endCount":
                return (e instanceof Connector k ? k.getConnectorEnd() : ((Type) e).getEndFeature()).size();
            case "endNames":
                return (e instanceof Connector k ? k.getConnectorEnd() : ((Type) e).getEndFeature())
                    .stream().map(Element::getName).toList();
            case "endReferences":
                return ((Connector) e).getConnectorEnd().stream().map(end -> {
                    ReferenceSubsetting rs = end.getOwnedReferenceSubsetting();
                    return rs == null ? null : chainForm(rs.getReferencedFeature());
                }).toList();
            case "sourceFeature": return chainForm(((Connector) e).getSourceFeature());
            case "targetFeature": return ((Connector) e).getTargetFeature().stream().map(MatricesTest::chainForm).toList();
            case "relatedFeature": return ((Connector) e).getRelatedFeature().stream().map(MatricesTest::chainForm).toList();
            case "typeIsConjugated": {
                List<Type> types = ((Feature) e).getType();
                return types.isEmpty() ? null : types.get(0) instanceof ConjugatedPortDefinition;
            }
            case "direction": {
                if (owner == null) {
                    FeatureDirectionKind own = ((Feature) e).getDirection();
                    return own == null ? null : own.getLiteral();
                }
                FeatureDirectionKind d = owner.directionOf((Feature) e);
                return d == null ? null : d.getLiteral();
            }
            case "isReference": return ((Usage) e).isReference();
            case "multiplicity": {
                Multiplicity m = ((Type) e).getMultiplicity();
                if (!(m instanceof MultiplicityRange r)) return m == null ? null : "<" + m.eClass().getName() + ">";
                Object upper = literal(r.getUpperBound());
                Object lower = r.getLowerBound() != null ? literal(r.getLowerBound()) : ("*".equals(upper) ? 0 : upper);
                return lower + ".." + upper;
            }
            case "value":
            case "isDefault": {
                // a value is the feature's owned membership of metaclass FeatureValue
                FeatureValue fv = e.getOwnedRelationship().stream().filter(r -> r instanceof FeatureValue)
                    .map(r -> (FeatureValue) r).findFirst().orElse(null);
                if (fv == null) return null;
                return check.equals("isDefault") ? fv.isDefault() : literal(fv.getValue());
            }
            default: throw new IllegalArgumentException("unknown check " + check);
        }
    }

    @AfterAll
    static void writeCsv() throws Exception {
        String dir = System.getProperty("resultsDir");
        Path out = Path.of(dir == null || dir.isEmpty() ? System.getProperty("dataDir") + "/../results" : dir);
        Files.createDirectories(out);
        StringBuilder sb = new StringBuilder("suite,matrix,id,outcome,detail\n");
        for (String[] r : rows) {
            sb.append(Arrays.stream(r).map(s -> "\"" + s.replace("\"", "\"\"").replace("\n", " ") + "\"")
                .collect(Collectors.joining(","))).append("\n");
        }
        Files.writeString(out.resolve("pilot-java.csv"), sb.toString());
    }
}
