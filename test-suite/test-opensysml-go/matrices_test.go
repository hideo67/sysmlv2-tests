// Every matrix in data/cases/*.json against the OpenSysML Go API (in process).
//
// Only the main APIs are used: LookupSymbol (the Symbol API) and Query
// (DISCUSSIONS.md, Step 3 decisions).
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
	ID      string            `json:"id"`
	Check   string            `json:"check"`
	Element string            `json:"element"`
	Through throughPath       `json:"through"`
	Expect  json.RawMessage   `json:"expect"`
	Accept  []json.RawMessage `json:"accept"`
	Unnamed *struct {
		Metaclass string `json:"metaclass"`
		Index     int    `json:"index"`
	} `json:"unnamed"`
}

type matrixSpec struct {
	Matrix string     `json:"matrix"`
	Model  string     `json:"model"`
	Cases  []caseSpec `json:"cases"`
}

// throughPath is the case's `through`: absent, one qualified name, or a path.
type throughPath []string

func (p *throughPath) UnmarshalJSON(b []byte) error {
	var one string
	if err := json.Unmarshal(b, &one); err == nil {
		*p = throughPath{one}
		return nil
	}
	var many []string
	if err := json.Unmarshal(b, &many); err != nil {
		return err
	}
	*p = many
	return nil
}

// norm compares qualified names without quoting: OpenSysML spells
// `CmdPort::~CmdPort` where the textual notation quotes `CmdPort::'~CmdPort'`.
func norm(qn string) string { return strings.ReplaceAll(qn, "'", "") }

var errUnsupported = errors.New("unsupported")

func unsupported(format string, args ...any) error {
	return fmt.Errorf("%w: "+format, append([]any{errUnsupported}, args...)...)
}

func TestMatrices(t *testing.T) {
	dataDir := filepath.Join("..", "data")
	files, err := filepath.Glob(filepath.Join(dataDir, "cases", "*.json"))
	if err != nil {
		t.Fatal(err)
	}
	ctx := context.Background()
	client, err := opensysml.New()
	if err != nil {
		t.Fatal(err)
	}
	defer client.Close()

	var rows [][]string
	defer func() { writeResults(t, rows) }()

	for _, file := range files {
		raw, err := os.ReadFile(file)
		if err != nil {
			t.Fatal(err)
		}
		var spec matrixSpec
		if err := json.Unmarshal(raw, &spec); err != nil {
			t.Fatal(err)
		}
		record := func(id, outcome, detail string) {
			detail = strings.Join(strings.Fields(detail), " ")
			rows = append(rows, []string{"opensysml-go", spec.Matrix, id, outcome, detail})
		}
		t.Run(spec.Matrix, func(t *testing.T) {
			model, err := client.ParseFile(ctx, filepath.Join(dataDir, spec.Model))
			if err != nil {
				t.Fatal(err)
			}
			for _, c := range spec.Cases {
				t.Run(c.ID, func(t *testing.T) {
					actual, err := doCheck(ctx, client, model, c)
					if errors.Is(err, errUnsupported) {
						record(c.ID, "unsupported", strings.TrimPrefix(strings.ReplaceAll(err.Error(), "\n", " "), "unsupported: "))
						t.Skipf("UNSUPPORTED: %v", err)
					}
					if err != nil {
						record(c.ID, "error", err.Error())
						t.Fatal(err)
					}
					got := normalize(actual)
					if matches(got, c.Expect) || slices.ContainsFunc(c.Accept, func(a json.RawMessage) bool { return matches(got, a) }) {
						record(c.ID, "pass", "")
						return
					}
					gotJSON, _ := json.Marshal(got)
					msg := fmt.Sprintf("%s %s: got %s, want %s", c.Check, c.Element, gotJSON, compact(c.Expect))
					record(c.ID, "fail", msg)
					t.Error(msg)
				})
			}
		})
	}
}

// normalize turns an adapter result into the shape encoding/json decodes to.
func normalize(v any) any {
	b, err := json.Marshal(v)
	if err != nil {
		return fmt.Sprint(v)
	}
	var out any
	_ = json.Unmarshal(b, &out)
	return out
}

func compact(raw json.RawMessage) string {
	var b strings.Builder
	for _, f := range strings.Fields(string(raw)) {
		b.WriteString(f)
	}
	return b.String()
}

func matches(got any, want json.RawMessage) bool {
	var w any
	if err := json.Unmarshal(want, &w); err != nil {
		return false
	}
	return reflect.DeepEqual(got, w)
}

func parent(qn string) string {
	if i := strings.LastIndex(qn, "::"); i >= 0 {
		return qn[:i]
	}
	return ""
}

func doCheck(ctx context.Context, cl opensysml.Client, m *opensysml.Model, c caseSpec) (any, error) {
	switch c.Check {
	case "isComposite", "isReference":
		_, err := cl.Query(ctx, m, opensysml.Query{Scope: []string{c.Element}, Select: []string{c.Check}})
		if err != nil {
			return nil, unsupported("%v", err)
		}
		return nil, errors.New("query accepted the property; extend the adapter")
	case "sourceFeature", "targetFeature", "relatedFeature":
		if c.Unnamed != nil {
			return nil, unsupported("the Symbol API has no connector features, and the query API cannot address an unnamed element")
		}
		_, err := cl.Query(ctx, m, opensysml.Query{Scope: []string{c.Element}, Select: []string{c.Check}})
		if err != nil {
			return nil, unsupported("%v", err)
		}
		return nil, errors.New("query accepted the property; extend the adapter")
	case "annotatedElement":
		return nil, unsupported("neither the Symbol nor the query API reports what a metadata usage annotates")
	case "payloadArgument", "senderArgument", "receiverArgument", "assignedFeature":
		return nil, unsupported("the Symbol API reports no arguments of an action")
	case "valueKind", "valueOperator", "valueReferences", "valueText":
		return nil, unsupported("the Symbol API reports a value only as a folded constant, with no expression structure or text")
	case "isDefault":
		return nil, unsupported("neither Symbol nor Attribute tells a default from a bound value")
	case "unnamedPartCount":
		scope := c.Element
		if len(c.Through) > 0 {
			scope = c.Through[0]
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
	owner := parent(c.Element)
	id := norm(c.Element)
	if len(c.Through) > 0 {
		// each step is read as a member the previous Symbol lists: as a child,
		// or (for attributes, own and inherited) in Attributes
		cur, err := cl.LookupSymbol(ctx, m, norm(c.Through[0]))
		if err != nil {
			return nil, err
		}
		steps := append([]string{}, c.Through[1:]...)
		if c.Unnamed == nil {
			steps = append(steps, c.Element)
		}
		for _, step := range steps {
			step = norm(step)
			name := step[strings.LastIndex(step, "::")+2:]
			visible := slices.Contains(cur.ChildIDs, step) ||
				slices.ContainsFunc(cur.Attributes, func(a opensysml.Attribute) bool { return a.Name == name })
			if !visible {
				return fmt.Sprintf("<%s not visible through %s>", step, cur.ID), nil
			}
			owner = cur.ID
			if cur, err = cl.LookupSymbol(ctx, m, step); err != nil {
				return nil, err
			}
		}
	}
	if c.Unnamed != nil {
		// the index-th unnamed member of the metaclass declared in c.Element
		ownerID := norm(c.Element)
		if len(c.Through) > 0 {
			ownerID = norm(c.Through[len(c.Through)-1])
		}
		o, err := cl.LookupSymbol(ctx, m, ownerID)
		if err != nil {
			return nil, err
		}
		var found []string
		for _, cid := range o.ChildIDs {
			ch, err := cl.LookupSymbol(ctx, m, cid)
			if err == nil && ch.Name == "" && strings.Contains(strings.ToLower(ch.Kind), strings.ToLower(c.Unnamed.Metaclass)) {
				found = append(found, cid)
			}
		}
		if len(found) <= c.Unnamed.Index {
			return fmt.Sprintf("<unnamed %s #%d of %s not listed>", c.Unnamed.Metaclass, c.Unnamed.Index, c.Element), nil
		}
		id = found[c.Unnamed.Index]
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
			return nil, unsupported("no type info")
		}
		return sym.Type.ResolvedID, nil
	case "metadataDefs", "metadataValue":
		// annotations an element lists: metadata-usage children (Symbol API), and
		// MetadataUsage rows the query API reports as owned by the element
		var symbols []*opensysml.Symbol
		for _, cid := range sym.ChildIDs {
			ch, err := cl.LookupSymbol(ctx, m, cid)
			if err == nil && strings.EqualFold(ch.Kind, "metadataUsage") {
				symbols = append(symbols, ch)
			}
		}
		if c.Check == "metadataValue" {
			if len(symbols) == 0 {
				return fmt.Sprintf("<no annotation of %s readable as a Symbol>", sym.ID), nil
			}
			for _, a := range symbols[0].Attributes {
				if a.Name == "severity" {
					return number(a.Value), nil
				}
			}
			return nil, nil
		}
		types := map[string]bool{}
		for _, s := range symbols {
			if s.Type != nil && s.Type.ResolvedID != "" {
				types[s.Type.ResolvedID] = true
			}
		}
		rows, err := cl.Query(ctx, m, opensysml.Query{Scope: []string{sym.ID}})
		if err != nil {
			return nil, err
		}
		for _, r := range rows {
			if r.Type == "MetadataUsage" && r.Properties["owner"] == sym.ID && r.Properties["type"] != "" {
				types[r.Properties["type"]] = true
			}
		}
		out := []string{}
		for k := range types {
			out = append(out, k)
		}
		slices.Sort(out)
		return out, nil
	case "kind":
		if sym.Kind == "" {
			return nil, nil
		}
		return strings.ToUpper(sym.Kind[:1]) + sym.Kind[1:], nil
	case "typeIsConjugated":
		if sym.Type == nil || sym.Type.ResolvedID == "" {
			return nil, nil
		}
		ty, err := cl.LookupSymbol(ctx, m, sym.Type.ResolvedID)
		if err != nil {
			return nil, err
		}
		// a conjugated port definition is named "~" + its original's name (SysML spec)
		return strings.HasPrefix(ty.Name, "~"), nil
	case "direction":
		// the member's direction as the Symbol reports it when listed through the port
		if d, ok := sym.Metadata["direction"]; ok {
			return d, nil
		}
		return nil, nil
	case "endCount", "endNames", "endReferences":
		if strings.HasSuffix(strings.ToLower(sym.Kind), "def") || strings.HasSuffix(sym.Kind, "Definition") {
			return nil, unsupported("the Symbol API does not mark the end features of a definition")
		}
		var refs [][]string
		names := []string{}
		for _, id := range sym.ChildIDs {
			end, err := cl.LookupSymbol(ctx, m, id)
			if err != nil || !strings.EqualFold(end.Kind, "connectorEnd") {
				continue
			}
			names = append(names, end.Name)
			// an end's reference is reported, if at all, as a subsets/references specialization
			r := []string{}
			for _, sp := range end.Specializations {
				if sp.Kind == "subsets" || sp.Kind == "references" {
					r = append(r, sp.TargetID)
				}
			}
			refs = append(refs, r)
		}
		if c.Check == "endCount" {
			return len(refs), nil
		}
		if c.Check == "endNames" {
			return names, nil
		}
		if refs == nil {
			return []any{}, nil
		}
		return refs, nil
	case "multiplicity":
		if sym.Multiplicity == nil {
			return nil, nil
		}
		lower := sym.Multiplicity.Lower
		if lower == "" {
			lower = sym.Multiplicity.Upper
			if lower == "*" {
				lower = "0"
			}
		}
		return lower + ".." + sym.Multiplicity.Upper, nil
	case "value":
		// a feature's value is reported in its owner's Attributes
		o, err := cl.LookupSymbol(ctx, m, owner)
		if err != nil {
			return nil, err
		}
		for _, a := range o.Attributes {
			if a.Name == sym.Name {
				return number(a.Value), nil
			}
		}
		return fmt.Sprintf("<%s not in Attributes of %s>", sym.Name, owner), nil
	}
	return nil, errors.New("unknown check " + c.Check)
}

func number(v opensysml.Value) any {
	switch x := v.(type) {
	case nil:
		return nil
	case opensysml.Real:
		return float64(x)
	case opensysml.Int:
		return float64(x)
	case opensysml.Rational:
		return x.Float64()
	default:
		return fmt.Sprintf("<%T %v>", v, v)
	}
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
