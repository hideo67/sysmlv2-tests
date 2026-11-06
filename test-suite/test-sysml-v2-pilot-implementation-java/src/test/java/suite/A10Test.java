package suite;

import static org.junit.jupiter.api.Assertions.*;
import static org.junit.jupiter.api.Assumptions.abort;

import com.google.gson.*;
import java.nio.file.*;
import java.util.*;
import java.util.stream.*;
import org.eclipse.emf.ecore.EObject;
import org.junit.jupiter.api.*;
import org.omg.sysml.interactive.SysMLInteractive;
import org.omg.sysml.lang.sysml.*;
import org.omg.sysml.util.ElementUtil;

/** Matrix A10 (part usages) against the Pilot Implementation's EMF model. */
class A10Test {
    static SysMLInteractive interactive;
    static JsonObject spec;

    @BeforeAll
    static void load() throws Exception {
        Path data = Path.of(System.getProperty("dataDir"));
        spec = JsonParser.parseString(Files.readString(data.resolve("cases/A10.json"))).getAsJsonObject();
        interactive = SysMLInteractive.createInstance();
        interactive.setVerbose(false);
        interactive.loadLibrary(Path.of(System.getProperty("libraryPath")).toAbsolutePath().toString());
        interactive.setResource("A10.sysml");
        interactive.parse(Files.readString(data.resolve(spec.get("model").getAsString())));
        assertTrue(interactive.validate().isEmpty(), "model has issues");
        ElementUtil.transformAll(interactive.getResource(), true);
    }

    @TestFactory
    Stream<DynamicTest> cases() {
        return StreamSupport.stream(spec.getAsJsonArray("cases").spliterator(), false)
            .map(e -> e.getAsJsonObject())
            .map(c -> DynamicTest.dynamicTest(c.get("id").getAsString(), () -> recorded(c)));
    }

    static final List<String[]> rows = new ArrayList<>();

    static void recorded(JsonObject c) {
        String id = c.get("id").getAsString();
        try {
            run(c);
            rows.add(new String[] {"pilot-java", "A10", id, "pass", ""});
        } catch (org.opentest4j.TestAbortedException e) {
            String why = String.valueOf(e.getMessage()).replaceFirst("^UNSUPPORTED: ", "");
            rows.add(new String[] {"pilot-java", "A10", id, "unsupported", why});
            throw e;
        } catch (AssertionError e) {
            rows.add(new String[] {"pilot-java", "A10", id, "fail", String.valueOf(e.getMessage())});
            throw e;
        } catch (RuntimeException e) {
            rows.add(new String[] {"pilot-java", "A10", id, "error", e.toString()});
            throw e;
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

    /** Finds an element by qualified name, descending through the root resource. */
    static Element find(String qn) {
        for (var it = interactive.getResource().getAllContents(); it.hasNext();) {
            EObject o = it.next();
            if (o instanceof Element e && qn.equals(e.getQualifiedName())) return e;
        }
        return null;
    }

    static void run(JsonObject c) {
        String check = c.get("check").getAsString();
        String qn = c.get("element").getAsString();
        String through = c.has("through") ? c.get("through").getAsString() : null;
        JsonElement expect = c.get("expect");
        if (check.equals("unnamedPartCount")) {
            Element scope = find(through != null ? through : qn);
            Collection<? extends Element> members = through != null
                ? ((Type) scope).getFeature() : ((Namespace) scope).getOwnedMember();
            long n = members.stream().filter(m -> m instanceof PartUsage)
                .filter(m -> m.getName() == null || m.getName().isEmpty())
                .filter(m -> m.getOwningNamespace() != null && qn.equals(m.getOwningNamespace().getQualifiedName())).count();
            assertEquals(expect.getAsInt(), n);
            return;
        }
        Element e;
        if (through == null) {
            e = find(qn);
            if (e == null) abort("UNSUPPORTED: no element " + qn);
        } else {
            e = ((Type) find(through)).getFeature().stream().filter(f -> qn.equals(f.getQualifiedName())).findFirst().orElse(null);
            if (e == null) fail("<" + qn + " not visible through " + through + ">");
        }
        switch (check) {
            case "name" -> assertEquals(expect.getAsString(), e.getName());
            case "type" -> assertEquals(expect.getAsString(), ((Feature) e).getType().get(0).getQualifiedName());
            case "isComposite" -> assertEquals(expect.getAsBoolean(), ((Feature) e).isComposite());
            case "isReference" -> assertEquals(expect.getAsBoolean(), ((Usage) e).isReference());
            default -> fail("unknown check " + check);
        }
    }
}
