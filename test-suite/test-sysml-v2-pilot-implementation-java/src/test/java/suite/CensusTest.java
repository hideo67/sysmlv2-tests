package suite;

import com.google.gson.*;
import java.nio.file.*;
import java.util.*;
import org.eclipse.emf.ecore.EObject;
import org.eclipse.emf.ecore.EStructuralFeature;
import org.eclipse.emf.ecore.resource.Resource;
import org.eclipse.xtext.diagnostics.Severity;
import org.eclipse.xtext.resource.XtextResource;
import org.eclipse.xtext.util.CancelIndicator;
import org.eclipse.xtext.validation.CheckMode;
import org.junit.jupiter.api.*;
import org.omg.sysml.interactive.SysMLInteractive;
import org.omg.sysml.lang.sysml.*;

/**
 * The derived-property census (data/gen_census.py) against the Pilot's EMF model: every
 * derived property of every element of each corpus, read with eGet. Runs only with CENSUS
 * set (run-census.sh); writes results/census-pilot-java.json.
 */
class CensusTest {
    @Test
    void census() throws Exception {
        Assumptions.assumeTrue(System.getenv("CENSUS") != null, "CENSUS not set");
        Path data = Path.of(System.getProperty("dataDir"));
        Path suiteDir = data.getParent();
        JsonObject spec = JsonParser.parseString(
            Files.readString(data.resolve("census/derived-properties.json"))).getAsJsonObject();
        JsonObject metaclasses = spec.getAsJsonObject("metaclasses");

        JsonObject out = new JsonObject();
        out.addProperty("suite", "pilot-java");
        JsonObject corporaOut = new JsonObject();
        out.add("corpora", corporaOut);
        for (Map.Entry<String, JsonElement> corpus : spec.getAsJsonObject("corpora").entrySet()) {
            SysMLInteractive interactive = SysMLInteractive.createInstance();
            interactive.setVerbose(false);
            interactive.loadLibrary(Path.of(System.getProperty("libraryPath")).toAbsolutePath().toString());
            List<Resource> docs = new ArrayList<>();
            for (JsonElement f : corpus.getValue().getAsJsonArray()) {
                Resource r = interactive.readResource(suiteDir.resolve(f.getAsString()).normalize().toString());
                interactive.addInputResource(r);
                docs.add(r);
            }
            // the elements as written: collected right after parsing, before resolution,
            // validation and transformAll, all of which can add implicit elements (feature-value
            // bindings, result parameters, default multiplicities, ...) under relationships
            // that are not marked implied; the values are read at the end, from the resolved and
            // transformed model, as the matrices adapter reads them
            Census census = new Census(metaclasses);
            List<Element> written = new ArrayList<>();
            for (Resource r : docs) {
                if (!r.getContents().isEmpty()) census.walk((Element) r.getContents().get(0), written);
            }
            interactive.resolveAllInputResources();
            JsonArray withErrors = new JsonArray();
            for (int i = 0; i < docs.size(); i++) {
                Resource r = docs.get(i);
                boolean error = ((XtextResource) r).getResourceServiceProvider().getResourceValidator()
                    .validate(r, CheckMode.ALL, CancelIndicator.NullImpl).stream()
                    .anyMatch(issue -> issue.getSeverity() == Severity.ERROR);
                if (error) withErrors.add(corpus.getValue().getAsJsonArray().get(i));
            }
            interactive.transformAll(true);
            for (Element e : written) census.measure(e);
            JsonObject c = census.toJson();
            c.addProperty("files", docs.size());
            c.add("filesWithErrors", withErrors);
            corporaOut.add(corpus.getKey(), c);
        }
        String dir = System.getProperty("resultsDir");
        Path results = Path.of(dir == null || dir.isEmpty() ? suiteDir.resolve("results").toString() : dir);
        Files.createDirectories(results);
        Files.writeString(results.resolve("census-pilot-java.json"),
            new GsonBuilder().setPrettyPrinting().create().toJson(out));
    }

    /** Counts per property and metaclass: carriers, non-empty, empty, unanswered, error. */
    static class Census {
        final JsonObject metaclasses;
        final Map<String, Map<String, int[]>> counts = new TreeMap<>();
        final Map<String, String> notes = new TreeMap<>();
        final Set<EObject> seen = Collections.newSetFromMap(new IdentityHashMap<>());
        final Map<String, Integer> unknownMetaclasses = new TreeMap<>();

        Census(JsonObject metaclasses) { this.metaclasses = metaclasses; }

        /** e, its non-implied owned relationships and their owned related elements, transitively. */
        void walk(Element root, List<Element> out) {
            Deque<Element> todo = new ArrayDeque<>(List.of(root));
            while (!todo.isEmpty()) {
                Element e = todo.pop();
                if (!seen.add(e)) continue;
                out.add(e);
                for (Relationship r : e.getOwnedRelationship()) {
                    if (r.isImplied()) continue;
                    todo.push(r);
                    for (Element x : r.getOwnedRelatedElement()) todo.push(x);
                }
            }
        }

        void measure(Element e) {
            String metaclass = e.eClass().getName();
            JsonArray keys = metaclasses.getAsJsonArray(metaclass);
            if (keys == null) {
                unknownMetaclasses.merge(metaclass, 1, Integer::sum);
                return;
            }
            for (JsonElement k : keys) {
                String key = k.getAsString();
                int[] n = counts.computeIfAbsent(key, x -> new TreeMap<>())
                    .computeIfAbsent(metaclass, x -> new int[5]);
                n[0]++;
                EStructuralFeature f = e.eClass().getEStructuralFeature(key.substring(key.indexOf("::") + 2));
                if (f == null) {
                    n[3]++;
                    notes.putIfAbsent(key, "no such feature on " + metaclass);
                    continue;
                }
                try {
                    Object v = e.eGet(f);
                    if (v == null || (v instanceof List<?> l && l.isEmpty()) || (v instanceof String s && s.isEmpty())) n[2]++;
                    else n[1]++;
                } catch (Throwable t) {
                    n[4]++;
                    notes.putIfAbsent(key, t.getClass().getSimpleName() + ": " + t.getMessage());
                }
            }
        }

        JsonObject toJson() {
            JsonObject c = new JsonObject();
            c.addProperty("elements", seen.size());
            JsonObject cs = new JsonObject();
            counts.forEach((key, byMeta) -> {
                JsonObject m = new JsonObject();
                byMeta.forEach((meta, n) -> {
                    JsonArray a = new JsonArray();
                    for (int x : n) a.add(x);
                    m.add(meta, a);
                });
                cs.add(key, m);
            });
            c.add("counts", cs);
            JsonObject ns = new JsonObject();
            notes.forEach(ns::addProperty);
            c.add("notes", ns);
            JsonObject um = new JsonObject();
            unknownMetaclasses.forEach(um::addProperty);
            c.add("unknownMetaclasses", um);
            return c;
        }
    }
}
