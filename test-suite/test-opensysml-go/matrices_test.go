// Every matrix in data/cases/*.json against the OpenSysML Go API (in process), in
// one of two readers, chosen by OPENSYSML_GO_SUITE:
//   opensysml-go (default): the Symbol API, this file;
//   opensysml-go-props: the element properties API (GetElementProperties), props_test.go.
//
// In suite opensysml-go only the Symbol API (LookupSymbol) is used: it is OpenSysML's element API, the
// counterpart of the Pilot's EMF model and sysml-toolkit's ResolvedModel
// (DISCUSSIONS.md, Step 5 decision). When the Symbol API has no field for a read, the
// result is unsupported, and the detail says whether the standard SysML v2 API &
// Services query API offers the property; Query is consulted for that note only,
// never for a value.
package suite

import (
	"bytes"
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
	Model   string            `json:"model"`
	Subject string            `json:"subject"`
	Path    string            `json:"path"`
	Path2   string            `json:"path2"`
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

// suite is the suite the results are written for, and check the reader it uses.
func suite() (string, func(context.Context, opensysml.Client, *opensysml.Model, caseSpec) (any, error)) {
	switch s := os.Getenv("OPENSYSML_GO_SUITE"); s {
	case "", "opensysml-go":
		return "opensysml-go", doCheck
	case "opensysml-go-props":
		return s, doCheckProps
	default:
		panic("OPENSYSML_GO_SUITE=" + s + ": expected opensysml-go or opensysml-go-props")
	}
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
	suiteName, check := suite()
	client, err := opensysml.New()
	if err != nil {
		t.Fatal(err)
	}
	defer client.Close()

	var rows [][]string
	defer func() { writeResults(t, suiteName, rows) }()

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
			rows = append(rows, []string{suiteName, spec.Matrix, id, outcome, detail})
		}
		t.Run(spec.Matrix, func(t *testing.T) {
			// each model is parsed once; a model the MDK reports errors for makes every
			// case that uses it an error
			models := map[string]*opensysml.Model{}
			rejectedBy := map[string]string{}
			load := func(file string) (*opensysml.Model, string) {
				if why, ok := rejectedBy[file]; ok {
					return nil, why
				}
				if mod, ok := models[file]; ok {
					return mod, ""
				}
				mod, err := client.ParseFile(ctx, filepath.Join(dataDir, file))
				if err != nil {
					rejectedBy[file] = "model not parsed: " + err.Error()
					return nil, rejectedBy[file]
				}
				var errs []string
				for _, d := range mod.Diagnostics {
					if d.Severity == opensysml.SeverityError && len(errs) < 2 {
						line := 0
						if d.Span != nil {
							line = d.Span.StartLine
						}
						errs = append(errs, fmt.Sprintf("line %d: %s", line, d.Message))
					}
				}
				if len(errs) > 0 {
					rejectedBy[file] = "model rejected: " + strings.Join(errs, "; ")
					return nil, rejectedBy[file]
				}
				models[file] = mod
				return mod, ""
			}
			for _, c := range spec.Cases {
				file := spec.Model
				if c.Model != "" {
					file = c.Model
				}
				model, why := load(file)
				if why != "" {
					record(c.ID, "error", why)
					t.Run(c.ID, func(t *testing.T) { t.Error(why) })
					continue
				}
				t.Run(c.ID, func(t *testing.T) {
					actual, err := check(ctx, client, model, c)
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
	var b bytes.Buffer
	if err := json.Compact(&b, raw); err != nil {
		return string(raw)
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
	case "instanceType", "instanceValue", "instanceCount", "endIdentity", "ownerPath":
		return instanceCheck(ctx, cl, m, c)
	case "evaluatedValue", "evaluatedUnit":
		// E10: the feature's value from the evaluation API, in its part def's scope or with
		// the usage as subject
		owner, name := parent(c.Element), c.Element[strings.LastIndex(c.Element, "::")+2:]
		opt := opensysml.WithContextSymbol(owner)
		if c.Subject != "" {
			opt = opensysml.WithSubject(c.Subject)
		}
		v, err := cl.Evaluate(ctx, m, name, opt)
		if err != nil {
			return fmt.Sprintf("<evaluation failed: %v>", err), nil
		}
		q, isQuantity := v.(opensysml.Quantity)
		if c.Check == "evaluatedUnit" {
			if isQuantity {
				return q.Unit, nil
			}
			return nil, nil
		}
		if isQuantity {
			return number(q.Magnitude), nil
		}
		switch x := v.(type) {
		case opensysml.Bool:
			return bool(x), nil
		case opensysml.String:
			return string(x), nil
		}
		return number(v), nil
	case "resolve":
		// the Symbol API's one name lookup: LookupSymbol(qualified name)
		s, err := lookupSym(ctx, cl, m, c.Element)
		if err != nil {
			if s, err = lookupSym(ctx, cl, m, norm(c.Element)); err != nil {
				return nil, nil
			}
		}
		return s.ID, nil
	case "entryKind", "doKind", "exitKind", "isParallel", "source", "target", "triggerPayload", "guardKind", "effectKind":
		prop := map[string]string{"entryKind": "entryAction", "doKind": "doAction", "exitKind": "exitAction", "isParallel": "isParallel", "source": "source", "target": "target", "triggerPayload": "triggerAction", "guardKind": "guardExpression", "effectKind": "effectAction"}[c.Check]
		return nil, noSymbolField(ctx, cl, m, c.Element, prop, prop)
	case "payloadTypes", "sourceOutput", "targetInput":
		prop := map[string]string{"payloadTypes": "payloadType", "sourceOutput": "sourceOutputFeature",
			"targetInput": "targetInputFeature"}[c.Check]
		return nil, noSymbolField(ctx, cl, m, c.Element, prop, "the flow's "+prop)
	case "shortName", "owner", "isIndividual", "result", "subject":
		// reads the Symbol API has no field for: unsupported, before the element is even
		// looked up (unsupported takes precedence over not being visible)
		nf := map[string][2]string{"shortName": {"shortName", "the short name"}, "owner": {"owner", "the owner"},
			"isIndividual": {"isIndividual", "isIndividual"}, "result": {"result", "the result parameter"},
			"subject": {"subjectParameter", "the subject parameter"}}[c.Check]
		return nil, noSymbolField(ctx, cl, m, norm(c.Element), nf[0], nf[1])
	case "documentation", "comments", "textualRepresentation":
		prop := map[string]string{"documentation": "documentation", "comments": "comment",
			"textualRepresentation": "textualRepresentation"}[c.Check]
		return nil, noSymbolField(ctx, cl, m, norm(c.Element), prop, c.Check)
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
	case "exprKind", "instantiatedType", "argumentCount", "argumentReferences", "hasResult", "resultType":
		return nil, unsupported("the Symbol API reports neither the arguments of an action nor expression structure, " +
			"so no constructor expression is reachable")
	case "isDefault":
		return nil, unsupported("neither Symbol nor Attribute tells a default from a bound value")
	case "unnamedPartCount":
		// unnamed part usages declared in c.Element, among the children the Symbol lists
		scope := norm(c.Element)
		if len(c.Through) > 0 {
			scope = norm(c.Through[len(c.Through)-1])
		}
		o, err := lookupSym(ctx, cl, m, scope)
		if err != nil {
			return nil, err
		}
		n := 0
		for _, cid := range scopeIDs(o, len(c.Through) > 0) {
			ch, err := lookupSym(ctx, cl, m, cid)
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
		// in Members (own and inherited), or (for attributes, own and inherited) in Attributes
		cur, err := lookupSym(ctx, cl, m, norm(c.Through[0]))
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
			visible := slices.Contains(memberIDs(cur), step) ||
				slices.ContainsFunc(cur.Attributes, func(a opensysml.Attribute) bool { return a.Name == name })
			if !visible {
				return fmt.Sprintf("<%s not visible through %s>", step, cur.ID), nil
			}
			owner = cur.ID
			if cur, err = lookupSym(ctx, cl, m, step); err != nil {
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
		o, err := lookupSym(ctx, cl, m, ownerID)
		if err != nil {
			return nil, err
		}
		var found []string
		for _, cid := range scopeIDs(o, len(c.Through) > 0) {
			if len(c.Through) > 0 && !strings.HasPrefix(cid, norm(c.Element)+"::") {
				continue
			}
			ch, err := lookupSym(ctx, cl, m, cid)
			if err == nil && ch.Name == "" && strings.Contains(strings.ToLower(ch.Kind), strings.ToLower(c.Unnamed.Metaclass)) {
				found = append(found, cid)
			}
		}
		if len(found) <= c.Unnamed.Index {
			return fmt.Sprintf("<unnamed %s #%d of %s not listed>", c.Unnamed.Metaclass, c.Unnamed.Index, c.Element), nil
		}
		id = found[c.Unnamed.Index]
	}
	sym, err := lookupSym(ctx, cl, m, id)
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
		// the derived Feature::type, most specific first (ResolvedID is the typing as written)
		if len(sym.Type.Types) == 0 {
			return "", nil
		}
		return sym.Type.Types[0].ID, nil
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
		// the derived Feature::type (ResolvedID is the typing as written)
		types := []string{}
		for _, t := range sym.Type.Types {
			types = append(types, t.ID)
		}
		slices.Sort(types)
		return types, nil
	case "idRoundTrip":
		again, err := lookupSym(ctx, cl, m, sym.ID)
		return err == nil && again.ID == sym.ID, nil
	case "substates":
		out := []string{}
		for _, cid := range sym.ChildIDs {
			ch, err := lookupSym(ctx, cl, m, cid)
			if err == nil && strings.EqualFold(ch.Kind, "stateUsage") {
				out = append(out, ch.Name)
			}
		}
		slices.Sort(out)
		return out, nil
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
			ch, err := lookupSym(ctx, cl, m, cid)
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
		// members the Symbol lists that it does not own: inherited Members, and
		// Attributes (own and inherited) not among the children
		inherited := []string{}
		seen := map[string]bool{}
		for _, mb := range sym.Members {
			// features only: Type::inheritedFeature, not inheritedMembership (a doc or comment is not)
			if mb.Inherited && !seen[mb.ID] && isFeatureKind(mb.Kind) {
				seen[mb.ID] = true
				inherited = append(inherited, mb.Name)
			}
		}
		for _, a := range sym.Attributes {
			if !slices.Contains(owned, a.Name) && !slices.Contains(inherited, a.Name) {
				inherited = append(inherited, a.Name)
			}
		}
		slices.Sort(inherited)
		return inherited, nil
	case "metadataDefs", "metadataValue":
		// annotations an element lists: its metadata-usage children
		var symbols []*opensysml.Symbol
		for _, cid := range sym.ChildIDs {
			ch, err := lookupSym(ctx, cl, m, cid)
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
	case "parameters":
		// members the Symbol lists (children and Members, own and inherited)
		// that carry a direction in their metadata
		out := [][]string{}
		for _, cid := range memberIDs(sym) {
			ch, err := lookupSym(ctx, cl, m, cid)
			if err == nil && ch.Metadata["direction"] != "" {
				out = append(out, []string{ch.Metadata["direction"], ch.Name})
			}
		}
		slices.SortFunc(out, func(a, b []string) int { return strings.Compare(a[0]+" "+a[1], b[0]+" "+b[1]) })
		return out, nil
	case "variants":
		// variant usages carry `variant: true` in their metadata
		out := []string{}
		for _, cid := range sym.ChildIDs {
			ch, err := lookupSym(ctx, cl, m, cid)
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
		ty, err := lookupSym(ctx, cl, m, sym.Type.ResolvedID)
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
			end, err := lookupSym(ctx, cl, m, id)
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
		o, err := lookupSym(ctx, cl, m, owner)
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

var instantiations = map[string]*opensysml.Instantiation{}

// instanceCheck is F10: walk c.Path from the object Instantiate(c.Element) builds.
func instanceCheck(ctx context.Context, cl opensysml.Client, m *opensysml.Model, c caseSpec) (any, error) {
	key := m.Hash + " " + c.Element
	inst, ok := instantiations[key]
	if !ok {
		var err error
		if inst, err = cl.Instantiate(ctx, m, c.Element); err != nil {
			return fmt.Sprintf("<instantiation failed: %v>", err), nil
		}
		instantiations[key] = inst
	}
	// walk returns the object (*Instance), a scalar Value, or a list of values at the path
	walk := func(path string) any {
		var cur any = inst.Root
		for _, name := range strings.Split(path, ".") {
			obj, ok := cur.(*opensysml.Instance)
			if !ok {
				return fmt.Sprintf("<%s: not an object>", name)
			}
			fv, ok := obj.FeatureValues[name]
			if !ok {
				return fmt.Sprintf("<no feature %s>", name)
			}
			resolve := func(v opensysml.Value) any {
				if id, ok := v.(opensysml.InstanceID); ok {
					return inst.Instance(id)
				}
				return v
			}
			if fv.Values != nil {
				list := []any{}
				for _, v := range fv.Values {
					list = append(list, resolve(v))
				}
				cur = list
			} else {
				cur = resolve(fv.Value)
			}
		}
		return cur
	}
	target := walk(c.Path)
	switch c.Check {
	case "ownerPath":
		// the object's path through its owners: of every path InstancePaths lists, the
		// first that steps through no connector end (an end reaches the object it
		// references, not one it owns)
		obj, ok := target.(*opensysml.Instance)
		if !ok {
			return fmt.Sprint(target), nil
		}
		paths, err := cl.InstancePaths(ctx, m, opensysml.ObjectRef{InstanceID: obj.ID})
		if err != nil {
			return fmt.Sprintf("<InstancePaths failed: %v>", err), nil
		}
	next:
		for _, p := range paths.Paths {
			for _, s := range p.Steps {
				if f, err := lookupSym(ctx, cl, m, s.FeatureSymbolID); err == nil && f.Kind == "connectorEnd" {
					continue next
				}
			}
			return p.Path, nil
		}
		return fmt.Sprintf("<no path to %s through owners only>", c.Path), nil
	case "instanceType":
		if obj, ok := target.(*opensysml.Instance); ok {
			return obj.TypeSymbolID, nil
		}
		return fmt.Sprint(target), nil
	case "instanceValue":
		if v, ok := target.(opensysml.Value); ok {
			return number(v), nil
		}
		return fmt.Sprint(target), nil
	case "instanceCount":
		if list, ok := target.([]any); ok {
			return len(list), nil
		}
		if _, ok := target.(*opensysml.Instance); ok {
			return 1, nil
		}
		return 0, nil
	}
	a, aok := target.(*opensysml.Instance)
	b, bok := walk(c.Path2).(*opensysml.Instance)
	return aok && bok && a.ID == b.ID, nil
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

func writeResults(t *testing.T, suite string, rows [][]string) {
	dir := os.Getenv("RESULTS_DIR")
	if dir == "" {
		dir = filepath.Join("..", "results")
	}
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Logf("results: %v", err)
		return
	}
	f, err := os.Create(filepath.Join(dir, suite+".csv"))
	if err != nil {
		t.Logf("results: %v", err)
		return
	}
	defer f.Close()
	w := csv.NewWriter(f)
	w.Write([]string{"suite", "matrix", "id", "outcome", "detail"})
	w.WriteAll(rows)
}

// memberIDs lists the ids of the members a Symbol lists: its children, then
// its Members (own and inherited; library-inherited ones are withheld).
// lookupSym is LookupSymbol with the members inherited from standard-library content
// listed in Members too (WithLibraryMembers), as Python lists them (DISCUSSIONS.md, Step 16).
func lookupSym(ctx context.Context, cl opensysml.Client, m *opensysml.Model, id string) (*opensysml.Symbol, error) {
	return cl.LookupSymbol(ctx, m, id, opensysml.WithLibraryMembers())
}

// scopeIDs lists where a member declared in an element is looked for: the children of the
// element itself, or, read through a usage (`part holder : Holder;`), the usage's children and
// Members, since what the usage gets from its definition are inherited memberships (as the
// Python harness reads them).
func scopeIDs(o *opensysml.Symbol, through bool) []string {
	if through {
		return memberIDs(o)
	}
	return o.ChildIDs
}

// nonFeatureKinds are the Symbol kinds that are not features
// (internal/semantic/symbols/symbol.go); every other kind, the usages above all, is a feature.
var nonFeatureKinds = map[string]bool{"documentation": true, "comment": true, "textualRepresentation": true,
	"alias": true, "dependency": true, "relationship": true, "namespace": true, "package": true,
	"kermlType": true, "metaclass": true}

func isFeatureKind(kind string) bool {
	return !nonFeatureKinds[kind] && !strings.HasSuffix(kind, "Def")
}

func memberIDs(sym *opensysml.Symbol) []string {
	out := append([]string{}, sym.ChildIDs...)
	for _, mb := range sym.Members {
		if !slices.Contains(out, mb.ID) {
			out = append(out, mb.ID)
		}
	}
	return out
}
