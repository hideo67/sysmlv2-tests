// Every matrix in data/cases/*.json against the OpenSysML Go API (in process).
//
// Only the Symbol API (LookupSymbol) is used: it is OpenSysML's element API, the
// counterpart of the Pilot's EMF model and sysml-toolkit's ResolvedModel
// (DISCUSSIONS.md, Step 5 decision). When the Symbol API has no field for a read, the
// result is unsupported, and the detail says whether the standard SysML v2 API &
// Services query API offers the property; Query is consulted for that note only,
// never for a value.
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
	Via     string            `json:"via"`
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

// noSymbolField is the unsupported result for a read the Symbol API has no field for;
// the detail notes whether the standard query API offers the property (consulted for
// that note only).
func noSymbolField(ctx context.Context, cl opensysml.Client, m *opensysml.Model, element, prop, what string) error {
	offered := false
	if rows, err := cl.Query(ctx, m, opensysml.Query{Scope: []string{element}, Select: []string{prop}}); err == nil {
		for _, r := range rows {
			if _, ok := r.Properties[prop]; ok {
				offered = true
			}
		}
	}
	note := "the standard query API does not offer it either"
	if offered {
		note = "available through the standard query API (" + prop + ")"
	}
	return unsupported("no Symbol field for %s; %s", what, note)
}

// Symbol kinds whose words are abbreviated (internal/semantic/symbols/symbol.go): `calc`,
// `enum`, and a binding, which is a BindingConnectorAsUsage.
var kindWords = map[string]string{"calc": "calculation", "enum": "enumeration"}
var kindWhole = map[string]string{"bindingUsage": "BindingConnectorAsUsage"}

// metaclassOf spells a Symbol kind as the spec metaclass: lower camel case, with `Def`
// for `Definition` and the abbreviations of kindWords expanded (`calcDef` -> `CalculationDefinition`).
func metaclassOf(kind string) string {
	if kind == "" {
		return ""
	}
	if whole, ok := kindWhole[kind]; ok {
		return whole
	}
	for short, full := range kindWords {
		if rest := strings.TrimPrefix(kind, short); rest != kind && rest != "" && rest[0] >= 'A' && rest[0] <= 'Z' {
			kind = full + rest
		}
	}
	if strings.HasSuffix(kind, "Def") {
		kind += "inition"
	}
	return strings.ToUpper(kind[:1]) + kind[1:]
}

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
	case "resolve":
		// the Symbol API's one name lookup: LookupSymbol(qualified name)
		s, err := cl.LookupSymbol(ctx, m, c.Element)
		if err != nil {
			if s, err = cl.LookupSymbol(ctx, m, norm(c.Element)); err != nil {
				return nil, nil
			}
		}
		return s.ID, nil
	case "payloadTypes", "sourceOutput", "targetInput":
		prop := map[string]string{"payloadTypes": "payloadType", "sourceOutput": "sourceOutputFeature",
			"targetInput": "targetInputFeature"}[c.Check]
		return nil, noSymbolField(ctx, cl, m, c.Element, prop, "the flow's "+prop)
	case "isComposite", "isReference":
		return nil, noSymbolField(ctx, cl, m, c.Element, c.Check, c.Check)
	case "sourceFeature", "targetFeature", "relatedFeature":
		if c.Unnamed != nil {
			return nil, unsupported("no Symbol field for %s; the query API cannot address an unnamed element", c.Check)
		}
		return nil, noSymbolField(ctx, cl, m, c.Element, c.Check, c.Check)
	case "allSupertypes":
		return nil, unsupported("neither the Symbol nor the query API gives the closure of supertypes")
	case "annotatedElement":
		return nil, unsupported("neither the Symbol nor the query API reports what a metadata usage annotates")
	case "payloadArgument", "senderArgument", "receiverArgument", "assignedFeature":
		return nil, unsupported("the Symbol API reports no arguments of an action")
	case "valueKind", "valueOperator", "valueReferences", "valueText":
		return nil, unsupported("the Symbol API reports a value only as a folded constant, with no expression structure or text")
	case "isDefault":
		return nil, unsupported("neither Symbol nor Attribute tells a default from a bound value")
	case "unnamedPartCount":
		// unnamed part usages declared in c.Element, among the children the Symbol lists
		scope := norm(c.Element)
		if len(c.Through) > 0 {
			scope = norm(c.Through[len(c.Through)-1])
		}
		o, err := cl.LookupSymbol(ctx, m, scope)
		if err != nil {
			return nil, err
		}
		n := 0
		for _, cid := range o.ChildIDs {
			ch, err := cl.LookupSymbol(ctx, m, cid)
			if err == nil && ch.Name == "" && strings.EqualFold(ch.Kind, "partUsage") && strings.HasPrefix(cid, norm(c.Element)+"::") {
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
	case "specializations", "subsettedFeatures":
		// OpenSysML's Specialization.Kind spelled as the spec metaclass
		kinds := map[string]string{"typing": "FeatureTyping", "subsets": "Subsetting", "redefines": "Redefinition",
			"references": "ReferenceSubsetting", "specializes": "Subclassification"}
		specs := [][]string{}
		subsetted := []string{}
		for _, sp := range sym.Specializations {
			k := sp.Kind
			if v, ok := kinds[k]; ok {
				k = v
			}
			specs = append(specs, []string{k, sp.TargetID})
			if k == "Subsetting" || k == "Redefinition" || k == "ReferenceSubsetting" {
				subsetted = append(subsetted, sp.TargetID)
			}
		}
		if c.Check == "subsettedFeatures" {
			slices.Sort(subsetted)
			return subsetted, nil
		}
		slices.SortFunc(specs, func(a, b []string) int { return strings.Compare(a[0]+" "+a[1], b[0]+" "+b[1]) })
		return specs, nil
	case "types":
		if sym.Type == nil {
			return nil, unsupported("no type info")
		}
		// TypeInfo reports one resolved type
		if sym.Type.ResolvedID == "" {
			return []string{}, nil
		}
		return []string{sym.Type.ResolvedID}, nil
	case "owner":
		return nil, noSymbolField(ctx, cl, m, sym.ID, "owner", "the owner")
	case "idRoundTrip":
		again, err := cl.LookupSymbol(ctx, m, sym.ID)
		return err == nil && again.ID == sym.ID, nil
	case "directGenerals":
		out := []string{}
		for _, sp := range sym.Specializations {
			if sp.Kind == "specializes" {
				out = append(out, sp.TargetID)
			}
		}
		slices.Sort(out)
		return out, nil
	case "ownedFeatureNames", "inheritedFeatureNames", "redefinitions":
		owned := []string{}
		redefs := [][]string{}
		for _, cid := range sym.ChildIDs {
			ch, err := cl.LookupSymbol(ctx, m, cid)
			if err != nil || strings.HasSuffix(strings.ToLower(ch.Kind), "def") {
				continue
			}
			owned = append(owned, ch.Name)
			for _, sp := range ch.Specializations {
				if sp.Kind == "redefines" {
					redefs = append(redefs, []string{ch.ID, sp.TargetID})
				}
			}
		}
		switch c.Check {
		case "ownedFeatureNames":
			slices.Sort(owned)
			return owned, nil
		case "redefinitions":
			slices.SortFunc(redefs, func(a, b []string) int { return strings.Compare(a[0]+a[1], b[0]+b[1]) })
			return redefs, nil
		}
		// members the Symbol lists that it does not own: Attributes (own and inherited) not among the children
		inherited := []string{}
		for _, a := range sym.Attributes {
			if !slices.Contains(owned, a.Name) {
				inherited = append(inherited, a.Name)
			}
		}
		slices.Sort(inherited)
		return inherited, nil
	case "metadataDefs", "metadataValue":
		// annotations an element lists: its metadata-usage children
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
		out := []string{}
		for k := range types {
			out = append(out, k)
		}
		slices.Sort(out)
		return out, nil
	case "kind":
		return metaclassOf(sym.Kind), nil
	case "shortName":
		return nil, noSymbolField(ctx, cl, m, sym.ID, "shortName", "the short name")
	case "isAbstract":
		// Symbol metadata carries `abstract: true` for an abstract element, nothing otherwise
		return sym.Metadata["abstract"] == "true", nil
	case "isVariation":
		return sym.Metadata["variation"] == "true", nil
	case "referenceTarget":
		if c.Via == "type" {
			if sym.Type == nil || sym.Type.ResolvedID == "" {
				return nil, nil
			}
			return sym.Type.ResolvedID, nil
		}
		for _, sp := range sym.Specializations {
			if sp.Kind == "subsets" {
				return sp.TargetID, nil
			}
		}
		return nil, nil
	case "result":
		return nil, noSymbolField(ctx, cl, m, sym.ID, "result", "the result parameter")
	case "subject":
		return nil, noSymbolField(ctx, cl, m, sym.ID, "subjectParameter", "the subject parameter")
	case "parameters":
		// children the Symbol lists that carry a direction in their metadata
		out := [][]string{}
		for _, cid := range sym.ChildIDs {
			ch, err := cl.LookupSymbol(ctx, m, cid)
			if err == nil && ch.Metadata["direction"] != "" {
				out = append(out, []string{ch.Metadata["direction"], ch.Name})
			}
		}
		slices.SortFunc(out, func(a, b []string) int { return strings.Compare(a[0]+" "+a[1], b[0]+" "+b[1]) })
		return out, nil
	case "isIndividual":
		return nil, noSymbolField(ctx, cl, m, sym.ID, "isIndividual", "isIndividual")
	case "variants":
		// variant usages carry `variant: true` in their metadata
		out := []string{}
		for _, cid := range sym.ChildIDs {
			ch, err := cl.LookupSymbol(ctx, m, cid)
			if err == nil && ch.Metadata["variant"] == "true" {
				out = append(out, ch.Name)
			}
		}
		slices.Sort(out)
		return out, nil
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
