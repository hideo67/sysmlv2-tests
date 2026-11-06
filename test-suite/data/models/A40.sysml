package A40 {
    part def T;
    part def V;

    part def Owner {
        part q : T;                 // the feature the others subset, reference or redefine
        part pTyped : T;            // feature typing
        part pSub :> q;             // subsetting
        ref part pRef ::> q;        // reference subsetting
        part pBoth : V :> q;        // feature typing and subsetting
    }
    part def SubOwner :> Owner {
        part :>> q;                 // redefinition (needs a specializing context)
    }
    part def SubSubOwner :> SubOwner;

    part owner : Owner;             // read through a typing usage
    part subOwner : SubOwner;       // ... through a usage of a specialized def (and typing usage of SubOwner)
    part subSub : SubSubOwner;      // ... through a usage of a def specializing SubOwner
}
