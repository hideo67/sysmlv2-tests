// The derived-property census (data/gen_census.py) against OpenSysML's element properties
// API (GetElementProperties), in process through the Go client, as suite opensysml-go-props
// reads a property. Runs only with CENSUS set (run-census.sh); writes
// results/census-opensysml-go-props.json.
package suite

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/Open-MBEE/OpenSysML/client/opensysml"
)

type censusSpec struct {
	Corpora     map[string][]string `json:"corpora"`
	Metaclasses map[string][]string `json:"metaclasses"`
}

// counts: carriers, non-empty, empty, unanswered, error
type census struct {
	Elements int                           `json:"elements"`
	Counts   map[string]map[string]*[5]int `json:"counts"`
	Notes    map[string]string             `json:"notes"`
	Unknown  map[string]int                `json:"unknownMetaclasses"`
	Files    int                           `json:"files"`
	Errors   []string                      `json:"filesWithErrors"`
	Excluded map[string]string             `json:"excludedByMdk"`
	seen     map[string]bool
}

func (c *census) note(key, why string) {
	if _, ok := c.Notes[key]; !ok {
		c.Notes[key] = strings.Join(strings.Fields(why), " ")
	}
}

func emptyValues(vs []opensysml.PropertyValue) bool {
	for _, v := range vs {
		if v.String != nil && *v.String == "" {
			continue
		}
		return false
	}
	return true
}

func (c *census) measure(ctx context.Context, cl opensysml.Client, m *opensysml.Model, e opensysml.ElementRef, keys []string) {
	names := make([]string, len(keys))
	for i, k := range keys {
		names[i] = k[strings.Index(k, "::")+2:]
	}
	r, err := cl.ElementProperties(ctx, m, e.ID, names...)
	for i, key := range keys {
		byMeta := c.Counts[key]
		if byMeta == nil {
			byMeta = map[string]*[5]int{}
			c.Counts[key] = byMeta
		}
		n := byMeta[e.Metaclass]
		if n == nil {
			n = &[5]int{}
			byMeta[e.Metaclass] = n
		}
		n[0]++
		if err != nil {
			n[4]++
			c.note(key, err.Error())
			continue
		}
		p := r.Property(names[i])
		switch {
		case p == nil:
			n[3]++
			c.note(key, "no entry in the answer")
		case p.DefiningClass == "":
			n[3]++
			c.note(key, "not declared on "+e.Metaclass+": "+p.Unsupported)
		case p.Unsupported != "":
			n[3]++
			c.note(key, p.Unsupported)
		case emptyValues(p.Values):
			n[2]++
		default:
			n[1]++
		}
	}
}

// walk: e, its non-implied owned relationships and their owned related elements, transitively.
func (c *census) walk(ctx context.Context, t *testing.T, cl opensysml.Client, m *opensysml.Model, metaclasses map[string][]string, start opensysml.ElementRef) {
	todo := []opensysml.ElementRef{start}
	for len(todo) > 0 {
		e := todo[len(todo)-1]
		todo = todo[:len(todo)-1]
		if c.seen[e.ID] {
			continue
		}
		c.seen[e.ID] = true
		c.Elements++
		if keys, ok := metaclasses[e.Metaclass]; ok {
			c.measure(ctx, cl, m, e, keys)
		} else {
			c.Unknown[e.Metaclass]++
		}
		r, err := cl.ElementProperties(ctx, m, e.ID, "ownedRelationship")
		if err != nil {
			t.Logf("ownedRelationship of %s: %v", e.ID, err)
			continue
		}
		owned := r.Property("ownedRelationship").Elements()
		for i := len(owned) - 1; i >= 0; i-- {
			rel, err := cl.ElementProperties(ctx, m, owned[i].ID, "isImplied", "ownedRelatedElement")
			if err != nil {
				t.Logf("relationship %s: %v", owned[i].ID, err)
				continue
			}
			if p := rel.Property("isImplied"); p != nil && len(p.Values) == 1 && p.Values[0].Bool != nil && *p.Values[0].Bool {
				continue
			}
			todo = append(todo, rel.Property("ownedRelatedElement").Elements()...)
			todo = append(todo, owned[i])
		}
	}
}

func TestCensus(t *testing.T) {
	if os.Getenv("CENSUS") == "" {
		t.Skip("CENSUS not set")
	}
	raw, err := os.ReadFile(filepath.Join("..", "data", "census", "derived-properties.json"))
	if err != nil {
		t.Fatal(err)
	}
	var spec censusSpec
	if err := json.Unmarshal(raw, &spec); err != nil {
		t.Fatal(err)
	}
	ctx := context.Background()
	cl, err := opensysml.New()
	if err != nil {
		t.Fatal(err)
	}
	defer cl.Close()

	out := map[string]any{"suite": "opensysml-go-props"}
	corpora := map[string]*census{}
	out["corpora"] = corpora
	for name, files := range spec.Corpora {
		paths := make([]string, len(files))
		for i, f := range files {
			paths[i] = filepath.Join("..", f)
		}
		c := &census{Counts: map[string]map[string]*[5]int{}, Notes: map[string]string{},
			Unknown: map[string]int{}, Files: len(files), Errors: []string{}, seen: map[string]bool{},
			Excluded: map[string]string{}}
		// a document with an error diagnostic makes GetElementProperties refuse the whole
		// model; such documents are left out (excludedByMdk) and the rest parsed again
		var m *opensysml.Model
		for {
			var err error
			m, err = cl.ParseFiles(ctx, paths)
			if err != nil {
				t.Fatalf("%s: %v", name, err)
			}
			bad := map[string]string{}
			for _, d := range m.Errors() {
				if d.Span == nil || d.Span.File == "" {
					c.Errors = append(c.Errors, "(no file): "+d.Message)
					continue
				}
				if _, ok := bad[d.Span.File]; !ok {
					bad[d.Span.File] = fmt.Sprintf("line %d: %s", d.Span.StartLine, d.Message)
				}
			}
			if len(bad) == 0 {
				break
			}
			var kept []string
			for _, p := range paths {
				if why, ok := bad[p]; ok {
					c.Excluded[strings.TrimPrefix(p, "../")] = why
				} else {
					kept = append(kept, p)
				}
			}
			if len(kept) == len(paths) {
				// errors in files not among the inputs: keep the model as it is
				for f, why := range bad {
					c.Errors = append(c.Errors, f+": "+why)
				}
				break
			}
			paths = kept
		}
		// each document's root namespace: the owning namespace of its top-level members
		for _, root := range m.Roots {
			for _, child := range root.ChildIDs {
				r, err := cl.ElementProperties(ctx, m, child, "owningNamespace")
				var fe *opensysml.FailureError
				if errors.As(err, &fe) {
					t.Logf("top-level %s: %v", child, err)
					continue
				}
				if err != nil {
					t.Fatal(err)
				}
				ns := r.Property("owningNamespace").Elements()
				if len(ns) == 1 {
					c.walk(ctx, t, cl, m, spec.Metaclasses, ns[0])
				} else {
					c.walk(ctx, t, cl, m, spec.Metaclasses, r.Element)
				}
			}
		}
		corpora[name] = c
		t.Logf("%s: %d elements", name, c.Elements)
	}
	dir := os.Getenv("RESULTS_DIR")
	if dir == "" {
		dir = filepath.Join("..", "results")
	}
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatal(err)
	}
	b, _ := json.MarshalIndent(out, "", " ")
	if err := os.WriteFile(filepath.Join(dir, "census-opensysml-go-props.json"), b, 0o644); err != nil {
		t.Fatal(err)
	}
}
