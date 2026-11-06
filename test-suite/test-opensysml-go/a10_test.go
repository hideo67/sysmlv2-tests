package suite

import (
	"context"
	"encoding/csv"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"slices"
	"strings"
	"testing"

	"github.com/Open-MBEE/OpenSysML/client/opensysml"
)

type caseSpec struct {
	ID      string          `json:"id"`
	Check   string          `json:"check"`
	Element string          `json:"element"`
	Through string          `json:"through"`
	Expect  json.RawMessage `json:"expect"`
}

type matrixSpec struct {
	Model string     `json:"model"`
	Cases []caseSpec `json:"cases"`
}

var errUnsupported = errors.New("unsupported")

func TestA10(t *testing.T) {
	dataDir := filepath.Join("..", "data")
	raw, err := os.ReadFile(filepath.Join(dataDir, "cases", "A10.json"))
	if err != nil {
		t.Fatal(err)
	}
	var spec matrixSpec
	if err := json.Unmarshal(raw, &spec); err != nil {
		t.Fatal(err)
	}
	ctx := context.Background()
	var rows [][]string
	defer func() { writeResults(t, rows) }()
	record := func(id, outcome, detail string) {
		rows = append(rows, []string{"opensysml-go", "A10", id, outcome, detail})
	}
	client, err := opensysml.New()
	if err != nil {
		t.Fatal(err)
	}
	defer client.Close()
	model, err := client.ParseFile(ctx, filepath.Join(dataDir, spec.Model))
	if err != nil {
		t.Fatal(err)
	}

	for _, c := range spec.Cases {
		t.Run(c.ID, func(t *testing.T) {
			actual, err := doCheck(ctx, client, model, c)
			if errors.Is(err, errUnsupported) {
				record(c.ID, "unsupported", strings.TrimPrefix(strings.ReplaceAll(err.Error(), "\n", " "), "unsupported "))
				t.Skipf("UNSUPPORTED: %v", err)
			}
			if err != nil {
				record(c.ID, "error", err.Error())
				t.Fatal(err)
			}
			var want any
			if err := json.Unmarshal(c.Expect, &want); err != nil {
				t.Fatal(err)
			}
			// JSON numbers decode as float64; normalize ints for comparison.
			if n, ok := actual.(int); ok {
				actual = float64(n)
			}
			if sl, ok := actual.([]string); ok {
				a := make([]any, len(sl))
				for i, s := range sl {
					a[i] = s
				}
				actual = a
			}
			if !reflect.DeepEqual(actual, want) {
				msg := fmt.Sprintf("%s %s: got %v, want %v", c.Check, c.Element, actual, want)
				record(c.ID, "fail", msg)
				t.Error(msg)
				return
			}
			record(c.ID, "pass", "")
		})
	}
}

func doCheck(ctx context.Context, cl opensysml.Client, m *opensysml.Model, c caseSpec) (any, error) {
	switch c.Check {
	case "isComposite", "isReference":
		_, err := cl.Query(ctx, m, opensysml.Query{Scope: []string{c.Element}, Select: []string{c.Check}})
		if err != nil {
			return nil, errors.Join(errUnsupported, err)
		}
		return nil, errors.New("query accepted the property; extend the adapter")
	case "unnamedPartCount":
		scope := c.Element
		if c.Through != "" {
			scope = c.Through
		}
		rows, err := cl.Query(ctx, m, opensysml.Query{Scope: []string{scope}})
		if err != nil {
			return nil, err
		}
		n := 0
		for _, r := range rows {
			if _, named := r.Properties["name"]; r.Type == "PartUsage" && r.Properties["owner"] == c.Element && !named {
				n++
			}
		}
		return n, nil
	}
	id := c.Element
	if c.Through != "" {
		// the member as seen from the usage: only what the usage's Symbol lists
		owner, err := cl.LookupSymbol(ctx, m, c.Through)
		if err != nil {
			return nil, err
		}
		if !slices.Contains(owner.ChildIDs, c.Element) {
			return fmt.Sprintf("<%s not visible through %s>", c.Element, c.Through), nil
		}
	}
	sym, err := cl.LookupSymbol(ctx, m, id)
	if err != nil {
		return nil, err
	}
	switch c.Check {
	case "name":
		return sym.Name, nil
	case "type":
		if sym.Type == nil {
			return nil, errors.Join(errUnsupported, errors.New("no type info"))
		}
		return sym.Type.ResolvedID, nil
	}
	return nil, errors.New("unknown check " + strings.TrimSpace(c.Check))
}

func writeResults(t *testing.T, rows [][]string) {
	dir := os.Getenv("RESULTS_DIR")
	if dir == "" {
		dir = filepath.Join("..", "results")
	}
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Logf("results: %v", err)
		return
	}
	f, err := os.Create(filepath.Join(dir, "opensysml-go.csv"))
	if err != nil {
		t.Logf("results: %v", err)
		return
	}
	defer f.Close()
	w := csv.NewWriter(f)
	w.Write([]string{"suite", "matrix", "id", "outcome", "detail"})
	w.WriteAll(rows)
}
