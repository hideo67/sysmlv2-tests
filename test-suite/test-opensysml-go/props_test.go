// The element properties reader (suite opensysml-go-props, OPENSYSML_GO_SUITE).
//
// Every model value comes from Client.ElementProperties, the GetElementProperties
// RPC: an element's KerML / SysML metamodel properties read by their specification
// names (DISCUSSIONS.md, Step 11). Each read takes the same route through the
// abstract syntax as test-opensysml-py/test_props.py and the sysml-toolkit adapter.
// The Symbol API is not used; the runtime reads (E10 evaluation, F10 instances) are
// those of suite opensysml-go.
//
// A property the service reports as not derived is unsupported, with the service's
// reason. A property the element's metaclass does not declare reads as empty. KerML
// operations (allSupertypes(), directionOf()) are not properties, so the reads that
// need them are unsupported.
package suite

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"strings"

	"github.com/Open-MBEE/OpenSysML/client/opensysml"
)

const noOperation = "GetElementProperties reads properties only; KerML operation %s is not served"

// unreadableError: the service named an element in an answer and cannot read it back.
type unreadableError struct{ msg string }

func (e *unreadableError) Error() string { return e.msg }

type propKey struct{ id, name string }

type propsAPI struct {
	ctx   context.Context
	cl    opensysml.Client
	m     *opensysml.Model
	props map[propKey]*opensysml.ElementProperty
	found map[string]*opensysml.ElementRef
	trees map[string][]opensysml.ElementRef
}

var propsAPIs = map[string]*propsAPI{}

func propsAPIOf(ctx context.Context, cl opensysml.Client, m *opensysml.Model) *propsAPI {
	if a, ok := propsAPIs[m.Hash]; ok {
		return a
	}
	a := &propsAPI{ctx: ctx, cl: cl, m: m, props: map[propKey]*opensysml.ElementProperty{},
		found: map[string]*opensysml.ElementRef{}, trees: map[string][]opensysml.ElementRef{}}
	propsAPIs[m.Hash] = a
	return a
}

// call is one GetElementProperties; a failure the service answers is not found or unreadable.
func (a *propsAPI) call(element string, names ...string) (*opensysml.ElementProperties, error) {
	r, err := a.cl.ElementProperties(a.ctx, a.m, element, names...)
	var fe *opensysml.FailureError
	if errors.As(err, &fe) {
		return nil, &unreadableError{fe.Message}
	}
	return r, err
}

// find is the element a qualified name (or positional or form id) names, or nil.
func (a *propsAPI) find(qn string) (*opensysml.ElementRef, error) {
	if e, ok := a.found[qn]; ok {
		return e, nil
	}
	var found *opensysml.ElementRef
	for _, name := range []string{qn, norm(qn)} {
		r, err := a.call(name, "name")
		var ue *unreadableError
		if errors.As(err, &ue) && strings.HasPrefix(ue.msg, "element not found") {
			continue
		}
		if err != nil {
			return nil, err
		}
		found = &r.Element
		break
	}
	a.found[qn] = found
	return found, nil
}

// read is the entries of names for element e, the missing ones fetched together.
func (a *propsAPI) read(e opensysml.ElementRef, names ...string) ([]*opensysml.ElementProperty, error) {
	var missing []string
	for _, n := range names {
		if _, ok := a.props[propKey{e.ID, n}]; !ok && !contains(missing, n) {
			missing = append(missing, n)
		}
	}
	if len(missing) > 0 {
		r, err := a.call(e.ID, missing...)
		if err != nil {
			return nil, err
		}
		for i := range r.Properties {
			p := r.Properties[i]
			a.props[propKey{e.ID, p.Name}] = &p
		}
	}
	out := make([]*opensysml.ElementProperty, 0, len(names))
	for _, n := range names {
		p := a.props[propKey{e.ID, n}]
		if p == nil {
			return nil, fmt.Errorf("no entry for %s of %s", n, e.ID)
		}
		if p.Unsupported != "" && p.DefiningClass != "" {
			return nil, unsupported("%s of %s: %s", n, e.Metaclass, p.Unsupported)
		}
		out = append(out, p)
	}
	return out, nil
}

func (a *propsAPI) elements(e opensysml.ElementRef, name string) ([]opensysml.ElementRef, error) {
	ps, err := a.read(e, name)
	if err != nil {
		return nil, err
	}
	return ps[0].Elements(), nil
}

func (a *propsAPI) element(e opensysml.ElementRef, name string) (*opensysml.ElementRef, error) {
	els, err := a.elements(e, name)
	if err != nil || len(els) == 0 {
		return nil, err
	}
	return &els[0], nil
}

// scalar is the one value of a property as a JSON-able value, nil when it has none.
func (a *propsAPI) scalar(e opensysml.ElementRef, name string) (any, error) {
	ps, err := a.read(e, name)
	if err != nil || len(ps[0].Values) == 0 {
		return nil, err
	}
	v := ps[0].Values[0]
	switch {
	case v.Bool != nil:
		return *v.Bool, nil
	case v.String != nil:
		return *v.String, nil
	case v.Int != nil:
		return *v.Int, nil
	case v.Real != nil:
		return *v.Real, nil
	case v.Number != nil:
		return *v.Number, nil
	case v.Element != nil:
		return v.Element.QualifiedName, nil
	}
	return nil, nil
}

// name is the element's name, nil when it is unnamed.
func (a *propsAPI) name(e opensysml.ElementRef) (any, error) { return a.scalar(e, "name") }

// nameText is the name, "" when unnamed.
func (a *propsAPI) nameText(e opensysml.ElementRef) (string, error) {
	n, err := a.name(e)
	s, _ := n.(string)
	return s, err
}

func qnOf(e *opensysml.ElementRef) any {
	if e == nil || e.QualifiedName == "" {
		return nil
	}
	return e.QualifiedName
}

// qnProp is the qualified name of the element property `prop` of e, nil when empty.
func (a *propsAPI) qnProp(e opensysml.ElementRef, prop string) (any, error) {
	x, err := a.element(e, prop)
	return qnOf(x), err
}

// visibleFeatures is everything visible in a type: the union of feature, ownedFeature,
// inheritedFeature and member, and the members of its inherited memberships.
func (a *propsAPI) visibleFeatures(t opensysml.ElementRef) ([]opensysml.ElementRef, error) {
	var out []opensysml.ElementRef
	seen := map[string]bool{}
	add := func(f opensysml.ElementRef) {
		if !seen[f.ID] {
			seen[f.ID] = true
			out = append(out, f)
		}
	}
	ps, err := a.read(t, "feature", "ownedFeature", "inheritedFeature", "member")
	if err != nil {
		return nil, err
	}
	for _, p := range ps {
		for _, f := range p.Elements() {
			add(f)
		}
	}
	mss, err := a.elements(t, "inheritedMembership")
	if err != nil {
		return nil, err
	}
	for _, ms := range mss {
		members, err := a.elements(ms, "memberElement")
		var ue *unreadableError
		if errors.As(err, &ue) {
			// a library membership the service lists but cannot read back
			// (DISCUSSIONS.md, Step 11); its member is usually also an inheritedFeature
			continue
		}
		if err != nil {
			return nil, err
		}
		for _, f := range members {
			add(f)
		}
	}
	return out, nil
}

// visibleStep is the member of cur whose qualified name is step, or nil.
func (a *propsAPI) visibleStep(cur opensysml.ElementRef, step string) (*opensysml.ElementRef, error) {
	fs, err := a.visibleFeatures(cur)
	if err != nil {
		return nil, err
	}
	for i := range fs {
		if norm(fs[i].QualifiedName) == norm(step) {
			return &fs[i], nil
		}
	}
	return nil, nil
}

// chainForm is a referenced feature as its chainingFeatures' qualified names.
func (a *propsAPI) chainForm(f opensysml.ElementRef) ([]any, error) {
	chain, err := a.elements(f, "chainingFeature")
	if err != nil {
		return nil, err
	}
	if len(chain) == 0 {
		chain = []opensysml.ElementRef{f}
	}
	out := []any{}
	for i := range chain {
		out = append(out, qnOf(&chain[i]))
	}
	return out, nil
}

func (a *propsAPI) featureValue(e opensysml.ElementRef) (*opensysml.ElementRef, error) {
	ms, err := a.elements(e, "ownedMembership")
	if err != nil {
		return nil, err
	}
	for i := range ms {
		if ms[i].Metaclass == "FeatureValue" {
			return &ms[i], nil
		}
	}
	return nil, nil
}

// valueExpr is the value expression of the feature's owned FeatureValue.
func (a *propsAPI) valueExpr(e opensysml.ElementRef) (*opensysml.ElementRef, error) {
	fv, err := a.featureValue(e)
	if err != nil || fv == nil {
		return nil, err
	}
	return a.element(*fv, "value")
}

// references are the referenced features of an expression, left to right, in chain form.
func (a *propsAPI) references(x opensysml.ElementRef) ([]any, error) {
	switch x.Metaclass {
	case "FeatureReferenceExpression":
		f, err := a.element(x, "referent")
		if err != nil || f == nil {
			return []any{}, err
		}
		c, err := a.chainForm(*f)
		return []any{c}, err
	case "FeatureChainExpression":
		args, err := a.elements(x, "argument")
		if err != nil {
			return nil, err
		}
		chain := []any{}
		if len(args) > 0 {
			refs, err := a.references(args[0])
			if err != nil {
				return nil, err
			}
			if len(refs) > 0 {
				if last, ok := refs[len(refs)-1].([]any); ok {
					chain = append(chain, last...)
				}
			}
		}
		t, err := a.element(x, "targetFeature")
		if err != nil {
			return nil, err
		}
		if t != nil {
			c, err := a.chainForm(*t)
			if err != nil {
				return nil, err
			}
			chain = append(chain, c...)
		}
		return []any{chain}, nil
	}
	out := []any{}
	args, err := a.elements(x, "argument")
	if err != nil {
		return nil, err
	}
	for _, arg := range args {
		refs, err := a.references(arg)
		if err != nil {
			return nil, err
		}
		out = append(out, refs...)
	}
	return out, nil
}

// tree is every element owned, directly or not, by the root package root.
func (a *propsAPI) tree(root string) ([]opensysml.ElementRef, error) {
	if t, ok := a.trees[root]; ok {
		return t, nil
	}
	start, err := a.find(root)
	if err != nil {
		return nil, err
	}
	var out []opensysml.ElementRef
	seen := map[string]bool{}
	var todo []opensysml.ElementRef
	if start != nil {
		todo = append(todo, *start)
	}
	for len(todo) > 0 {
		cur := todo[len(todo)-1]
		todo = todo[:len(todo)-1]
		if seen[cur.ID] {
			continue
		}
		seen[cur.ID] = true
		out = append(out, cur)
		owned, err := a.elements(cur, "ownedElement")
		if err != nil {
			return nil, err
		}
		for i := len(owned) - 1; i >= 0; i-- {
			todo = append(todo, owned[i])
		}
	}
	a.trees[root] = out
	return out, nil
}

// annotating is the elements of metaclass in e's root package whose annotatedElement includes e.
func (a *propsAPI) annotating(e opensysml.ElementRef, metaclass string) ([]opensysml.ElementRef, error) {
	root := strings.Split(e.QualifiedName, "::")[0]
	all, err := a.tree(root)
	if err != nil {
		return nil, err
	}
	var out []opensysml.ElementRef
	for _, x := range all {
		if x.Metaclass != metaclass {
			continue
		}
		ann, err := a.elements(x, "annotatedElement")
		if err != nil {
			return nil, err
		}
		for _, y := range ann {
			if y.ID == e.ID {
				out = append(out, x)
				break
			}
		}
	}
	return out, nil
}

func (a *propsAPI) body(c opensysml.ElementRef) (string, error) {
	b, err := a.scalar(c, "body")
	s, _ := b.(string)
	return strings.TrimSpace(s), err
}

func (a *propsAPI) literal(x opensysml.ElementRef) (any, error) {
	if x.Metaclass == "LiteralInfinity" {
		return "*", nil
	}
	return a.scalar(x, "value")
}

func (a *propsAPI) implied(r opensysml.ElementRef) (bool, error) {
	v, err := a.scalar(r, "isImplied")
	return v == true, err
}

// sortJSON sorts values by their JSON text, as the Python suite sorts them.
func sortJSON(xs []any) []any {
	sort.SliceStable(xs, func(i, j int) bool {
		a, _ := json.Marshal(xs[i])
		b, _ := json.Marshal(xs[j])
		return string(a) < string(b)
	})
	return xs
}

func contains(xs []string, s string) bool {
	for _, x := range xs {
		if x == s {
			return true
		}
	}
	return false
}

// doCheckProps reads one case through GetElementProperties; an element the service
// cannot read back makes the case fail with the service's message as the value.
func doCheckProps(ctx context.Context, cl opensysml.Client, m *opensysml.Model, c caseSpec) (any, error) {
	v, err := propsCheck(ctx, cl, m, c)
	var ue *unreadableError
	if errors.As(err, &ue) {
		return "<unreadable element: " + ue.msg + ">", nil
	}
	return v, err
}

func propsCheck(ctx context.Context, cl opensysml.Client, m *opensysml.Model, c caseSpec) (any, error) {
	switch c.Check {
	case "instanceType", "instanceValue", "instanceCount", "endIdentity", "ownerPath",
		"evaluatedValue", "evaluatedUnit":
		return doCheck(ctx, cl, m, c) // the runtime API, as suite opensysml-go reads it
	}
	a := propsAPIOf(ctx, cl, m)
	path := []string(c.Through)
	switch c.Check {
	case "resolve":
		// the element id is resolved as a qualified name; a name that resolves to a
		// Membership (an alias) stands for its memberElement
		found, err := a.find(c.Element)
		if err != nil || found == nil {
			return nil, err
		}
		if strings.HasSuffix(found.Metaclass, "Membership") {
			return a.qnProp(*found, "memberElement")
		}
		return qnOf(found), nil
	case "allSupertypes":
		return nil, unsupported(noOperation, "Type::allSupertypes()")
	case "valueText":
		return nil, unsupported("no property holds an expression's source text")
	case "unnamedPartCount":
		scopeName := c.Element
		if len(path) > 0 {
			scopeName = path[0]
		}
		scope, err := a.find(scopeName)
		if err != nil {
			return nil, err
		}
		if scope == nil {
			return "<no element " + scopeName + ">", nil
		}
		var members []opensysml.ElementRef
		if len(path) > 0 {
			members, err = a.visibleFeatures(*scope)
		} else {
			members, err = a.elements(*scope, "ownedMember")
		}
		if err != nil {
			return nil, err
		}
		n := 0
		for _, mb := range members {
			if mb.Metaclass != "PartUsage" {
				continue
			}
			name, err := a.name(mb)
			if err != nil {
				return nil, err
			}
			owner, err := a.qnProp(mb, "owningNamespace")
			if err != nil {
				return nil, err
			}
			if mb.Metaclass == "PartUsage" && name == nil && owner == c.Element {
				n++
			}
		}
		return n, nil
	}

	// the element, read through each step of the path as a member visible in the previous one
	var owner *opensysml.ElementRef
	var e opensysml.ElementRef
	switch {
	case c.Unnamed != nil:
		var scope *opensysml.ElementRef
		var members []opensysml.ElementRef
		var err error
		if len(path) == 0 {
			if scope, err = a.find(c.Element); err != nil {
				return nil, err
			}
			if scope == nil {
				return "<no element " + c.Element + ">", nil
			}
			members, err = a.elements(*scope, "ownedMember")
		} else {
			if scope, err = a.find(path[0]); err != nil || scope == nil {
				return fmt.Sprintf("<no element %s>", path[0]), err
			}
			for _, step := range path[1:] {
				if scope, err = a.visibleStep(*scope, step); err != nil {
					return nil, err
				}
				if scope == nil {
					return "<" + step + " not visible>", nil
				}
			}
			members, err = a.visibleFeatures(*scope)
		}
		if err != nil {
			return nil, err
		}
		var found []opensysml.ElementRef
		for _, mb := range members {
			name, err := a.name(mb)
			if err != nil {
				return nil, err
			}
			if name != nil || !strings.Contains(mb.Metaclass, c.Unnamed.Metaclass) {
				continue
			}
			ow, err := a.qnProp(mb, "owningNamespace")
			if err != nil {
				return nil, err
			}
			if ow == c.Element {
				found = append(found, mb)
			}
		}
		owner = scope
		if len(found) <= c.Unnamed.Index {
			return fmt.Sprintf("<unnamed %s #%d of %s not listed>", c.Unnamed.Metaclass, c.Unnamed.Index, c.Element), nil
		}
		e = found[c.Unnamed.Index]
	case len(path) == 0:
		found, err := a.find(c.Element)
		if err != nil {
			return nil, err
		}
		if found == nil {
			return nil, unsupported("no element %s", c.Element)
		}
		e = *found
	default:
		cur, err := a.find(path[0])
		if err != nil {
			return nil, err
		}
		if cur == nil {
			return nil, fmt.Errorf("no element %s", path[0])
		}
		for _, step := range append(append([]string{}, path[1:]...), c.Element) {
			nxt, err := a.visibleStep(*cur, step)
			if err != nil {
				return nil, err
			}
			if nxt == nil {
				return fmt.Sprintf("<%s not visible through %v>", step, qnOf(cur)), nil
			}
			owner, cur = cur, nxt
		}
		e = *cur
	}
	return propsRead(a, c, e, owner)
}

// names is the sorted names (or "") of the elements els.
func (a *propsAPI) names(els []opensysml.ElementRef) ([]any, error) {
	out := []any{}
	for _, x := range els {
		n, err := a.nameText(x)
		if err != nil {
			return nil, err
		}
		out = append(out, n)
	}
	return sortJSON(out), nil
}

func propsRead(a *propsAPI, c caseSpec, e opensysml.ElementRef, owner *opensysml.ElementRef) (any, error) {
	switch c.Check {
	case "name":
		return a.name(e)
	case "kind":
		return e.Metaclass, nil
	case "type", "source", "target":
		return a.qnProp(e, c.Check)
	case "isComposite", "isReference", "shortName", "isAbstract", "isVariation", "isIndividual", "isParallel":
		return a.scalar(e, c.Check)
	case "documentation", "comments":
		var docs []opensysml.ElementRef
		var err error
		if c.Check == "documentation" {
			docs, err = a.elements(e, "documentation")
		} else {
			docs, err = a.annotating(e, "Comment")
		}
		if err != nil {
			return nil, err
		}
		out := []any{}
		for _, d := range docs {
			b, err := a.body(d)
			if err != nil {
				return nil, err
			}
			out = append(out, b)
		}
		return sortJSON(out), nil
	case "textualRepresentation":
		reps, err := a.elements(e, "textualRepresentation")
		if err != nil {
			return nil, err
		}
		out := []any{}
		for _, r := range reps {
			lang, err := a.scalar(r, "language")
			if err != nil {
				return nil, err
			}
			b, err := a.body(r)
			if err != nil {
				return nil, err
			}
			out = append(out, []any{lang, b})
		}
		return sortJSON(out), nil
	case "entryKind", "doKind", "exitKind", "guardKind", "effectKind":
		prop := map[string]string{"entryKind": "entryAction", "doKind": "doAction", "exitKind": "exitAction",
			"guardKind": "guardExpression", "effectKind": "effectAction"}[c.Check]
		x, err := a.element(e, prop)
		if err != nil || x == nil {
			return nil, err
		}
		return x.Metaclass, nil
	case "substates":
		fs, err := a.elements(e, "ownedFeature")
		if err != nil {
			return nil, err
		}
		var states []opensysml.ElementRef
		for _, f := range fs {
			if f.Metaclass == "StateUsage" {
				states = append(states, f)
			}
		}
		return a.names(states)
	case "triggerPayload":
		acc, err := a.element(e, "triggerAction")
		if err != nil || acc == nil {
			return nil, err
		}
		p, err := a.element(*acc, "payloadParameter")
		if err != nil || p == nil {
			return nil, err
		}
		return a.qnProp(*p, "type")
	case "payloadTypes", "types":
		prop := "payloadType"
		if c.Check == "types" {
			prop = "type"
		}
		ts, err := a.elements(e, prop)
		if err != nil {
			return nil, err
		}
		out := []any{}
		for i := range ts {
			out = append(out, qnOf(&ts[i]))
		}
		return sortJSON(out), nil
	case "sourceOutput", "targetInput":
		prop := "sourceOutputFeature"
		if c.Check == "targetInput" {
			prop = "targetInputFeature"
		}
		f, err := a.element(e, prop)
		if err != nil || f == nil {
			return nil, err
		}
		rs, err := a.elements(*f, "ownedRedefinition")
		if err != nil {
			return nil, err
		}
		var target any
		for _, r := range rs {
			t, err := a.qnProp(r, "redefinedFeature")
			if err != nil {
				return nil, err
			}
			if t != nil {
				target = t
			}
		}
		return target, nil
	case "referenceTarget":
		if c.Via == "type" {
			return a.qnProp(e, "type")
		}
		rs, err := a.elements(e, "ownedSubsetting")
		if err != nil {
			return nil, err
		}
		for _, r := range rs {
			imp, err := a.implied(r)
			if err != nil {
				return nil, err
			}
			t, err := a.qnProp(r, "subsettedFeature")
			if err != nil {
				return nil, err
			}
			if !imp && t != nil {
				return t, nil
			}
		}
		return nil, nil
	case "specializations", "subsettedFeatures":
		prop := "ownedSpecialization"
		if c.Check == "subsettedFeatures" {
			prop = "ownedSubsetting"
		}
		rs, err := a.elements(e, prop)
		if err != nil {
			return nil, err
		}
		generalProp := map[string]string{"FeatureTyping": "type", "ConjugatedPortTyping": "type",
			"Subsetting": "subsettedFeature", "Redefinition": "redefinedFeature",
			"ReferenceSubsetting": "referencedFeature", "Subclassification": "superclassifier"}
		out := []any{}
		for _, r := range rs {
			imp, err := a.implied(r)
			if err != nil {
				return nil, err
			}
			if imp {
				continue
			}
			gp, ok := generalProp[r.Metaclass]
			if !ok {
				gp = "general"
			}
			g, err := a.qnProp(r, gp)
			if err != nil {
				return nil, err
			}
			if g == nil {
				if g, err = a.qnProp(r, "general"); err != nil {
					return nil, err
				}
			}
			if c.Check == "specializations" {
				out = append(out, []any{r.Metaclass, g})
			} else if g != nil {
				out = append(out, g)
			}
		}
		return sortJSON(out), nil
	case "owner":
		return a.qnProp(e, "owningNamespace")
	case "idRoundTrip":
		r, err := a.call(e.ID, "name")
		if err != nil {
			return nil, err
		}
		return r.Element.ID == e.ID, nil
	case "directGenerals":
		rs, err := a.elements(e, "ownedSubclassification")
		if err != nil {
			return nil, err
		}
		out := []any{}
		for _, r := range rs {
			imp, err := a.implied(r)
			if err != nil {
				return nil, err
			}
			if imp {
				continue
			}
			g, err := a.qnProp(r, "superclassifier")
			if err != nil {
				return nil, err
			}
			out = append(out, g)
		}
		return sortJSON(out), nil
	case "ownedFeatureNames", "inheritedFeatureNames":
		prop := "ownedFeature"
		if c.Check == "inheritedFeatureNames" {
			prop = "inheritedFeature"
		}
		fs, err := a.elements(e, prop)
		if err != nil {
			return nil, err
		}
		return a.names(fs)
	case "redefinitions":
		fs, err := a.elements(e, "ownedFeature")
		if err != nil {
			return nil, err
		}
		out := []any{}
		for i := range fs {
			rs, err := a.elements(fs[i], "ownedRedefinition")
			if err != nil {
				return nil, err
			}
			for _, r := range rs {
				t, err := a.qnProp(r, "redefinedFeature")
				if err != nil {
					return nil, err
				}
				out = append(out, []any{qnOf(&fs[i]), t})
			}
		}
		return sortJSON(out), nil
	case "parameters":
		// each directed feature's own direction (directionOf is an operation)
		fs, err := a.elements(e, "directedFeature")
		if err != nil {
			return nil, err
		}
		out := []any{}
		for _, f := range fs {
			dir, err := a.scalar(f, "direction")
			if err != nil {
				return nil, err
			}
			n, err := a.nameText(f)
			if err != nil {
				return nil, err
			}
			out = append(out, []any{dir, n})
		}
		return sortJSON(out), nil
	case "result", "subject":
		prop := "result"
		if c.Check == "subject" {
			prop = "subjectParameter"
		}
		p, err := a.element(e, prop)
		if err != nil || p == nil {
			return nil, err
		}
		return a.name(*p)
	case "variants":
		vs, err := a.elements(e, "variant")
		if err != nil {
			return nil, err
		}
		return a.names(vs)
	case "metadataDefs", "metadataValue", "annotatedElement":
		mus, err := a.annotating(e, "MetadataUsage")
		if err != nil {
			return nil, err
		}
		if c.Check == "metadataDefs" {
			out := []any{}
			for _, mu := range mus {
				d, err := a.qnProp(mu, "metadataDefinition")
				if err != nil {
					return nil, err
				}
				out = append(out, d)
			}
			return sortJSON(out), nil
		}
		if len(mus) == 0 {
			return "<no annotation of " + c.Element + " found>", nil
		}
		if c.Check == "annotatedElement" {
			els, err := a.elements(mus[0], "annotatedElement")
			if err != nil {
				return nil, err
			}
			out := []any{}
			for i := range els {
				out = append(out, qnOf(&els[i]))
			}
			return out, nil
		}
		fs, err := a.elements(mus[0], "ownedFeature")
		if err != nil {
			return nil, err
		}
		var v any
		for _, f := range fs {
			n, err := a.name(f)
			if err != nil {
				return nil, err
			}
			if n != "severity" {
				continue
			}
			x, err := a.valueExpr(f)
			if err != nil {
				return nil, err
			}
			if x != nil {
				if v, err = a.literal(*x); err != nil {
					return nil, err
				}
			}
		}
		return v, nil
	case "payloadArgument", "senderArgument", "receiverArgument":
		x, err := a.element(e, c.Check)
		if err != nil || x == nil {
			return nil, err
		}
		return a.references(*x)
	case "assignedFeature":
		f, err := a.element(e, "referent")
		if err != nil || f == nil {
			return nil, err
		}
		return a.chainForm(*f)
	case "exprKind", "instantiatedType", "argumentCount", "argumentReferences", "hasResult", "resultType":
		var x *opensysml.ElementRef
		var err error
		if e.Metaclass == "SendActionUsage" {
			x, err = a.element(e, "payloadArgument")
		} else {
			x, err = a.valueExpr(e)
		}
		if err != nil || x == nil {
			return nil, err
		}
		switch c.Check {
		case "exprKind":
			return x.Metaclass, nil
		case "instantiatedType":
			return a.qnProp(*x, "instantiatedType")
		case "argumentCount":
			args, err := a.elements(*x, "argument")
			return len(args), err
		case "argumentReferences":
			args, err := a.elements(*x, "argument")
			if err != nil {
				return nil, err
			}
			out := []any{}
			for _, arg := range args {
				refs, err := a.references(arg)
				if err != nil {
					return nil, err
				}
				out = append(out, refs...)
			}
			return out, nil
		}
		r, err := a.element(*x, "result")
		if err != nil {
			return nil, err
		}
		if c.Check == "hasResult" {
			return r != nil, nil
		}
		if r == nil {
			return nil, nil
		}
		return a.qnProp(*r, "type")
	case "valueKind", "valueOperator", "valueReferences":
		x, err := a.valueExpr(e)
		if err != nil || x == nil {
			return nil, err
		}
		switch c.Check {
		case "valueKind":
			return x.Metaclass, nil
		case "valueOperator":
			return a.scalar(*x, "operator") // empty when the metaclass declares no operator
		}
		return a.references(*x)
	case "endCount", "endNames":
		prop := "connectorEnd"
		if strings.HasSuffix(e.Metaclass, "Definition") {
			prop = "endFeature"
		}
		ends, err := a.elements(e, prop)
		if err != nil {
			return nil, err
		}
		if c.Check == "endCount" {
			return len(ends), nil
		}
		out := []any{}
		for _, x := range ends {
			n, err := a.name(x)
			if err != nil {
				return nil, err
			}
			out = append(out, n)
		}
		return out, nil
	case "endReferences":
		ends, err := a.elements(e, "connectorEnd")
		if err != nil {
			return nil, err
		}
		out := []any{}
		for _, end := range ends {
			rs, err := a.element(end, "ownedReferenceSubsetting")
			if err != nil {
				return nil, err
			}
			var f *opensysml.ElementRef
			if rs != nil {
				if f, err = a.element(*rs, "referencedFeature"); err != nil {
					return nil, err
				}
			}
			if f == nil {
				out = append(out, nil)
				continue
			}
			cf, err := a.chainForm(*f)
			if err != nil {
				return nil, err
			}
			out = append(out, cf)
		}
		return out, nil
	case "sourceFeature":
		f, err := a.element(e, "sourceFeature")
		if err != nil || f == nil {
			return nil, err
		}
		return a.chainForm(*f)
	case "targetFeature", "relatedFeature":
		fs, err := a.elements(e, c.Check)
		if err != nil {
			return nil, err
		}
		out := []any{}
		for _, f := range fs {
			cf, err := a.chainForm(f)
			if err != nil {
				return nil, err
			}
			out = append(out, cf)
		}
		return out, nil
	case "typeIsConjugated":
		t, err := a.element(e, "type")
		if err != nil || t == nil {
			return nil, err
		}
		return t.Metaclass == "ConjugatedPortDefinition", nil
	case "direction":
		if owner != nil {
			return nil, unsupported(noOperation, "Type::directionOf(feature)")
		}
		return a.scalar(e, "direction")
	case "multiplicity":
		mult, err := a.element(e, "multiplicity")
		if err != nil || mult == nil {
			return nil, err
		}
		var upper, lower any
		if u, err := a.element(*mult, "upperBound"); err != nil {
			return nil, err
		} else if u != nil {
			if upper, err = a.literal(*u); err != nil {
				return nil, err
			}
		}
		if l, err := a.element(*mult, "lowerBound"); err != nil {
			return nil, err
		} else if l != nil {
			if lower, err = a.literal(*l); err != nil {
				return nil, err
			}
		} else if upper == "*" {
			lower = 0
		} else {
			lower = upper
		}
		return fmt.Sprintf("%v..%v", bound(lower), bound(upper)), nil
	case "value", "isDefault":
		fv, err := a.featureValue(e)
		if err != nil || fv == nil {
			return nil, err
		}
		if c.Check == "isDefault" {
			return a.scalar(*fv, "isDefault")
		}
		x, err := a.element(*fv, "value")
		if err != nil || x == nil {
			return nil, err
		}
		return a.literal(*x)
	}
	return nil, errors.New("unknown check " + c.Check)
}

// bound spells a multiplicity bound as the Python suite does (None for a missing one).
func bound(v any) string {
	if v == nil {
		return "None"
	}
	return fmt.Sprint(v)
}
