package A03 {
    // each modifier on each kind of definition that accepts all of them
    // (OccurrenceDefinitionPrefix in the grammar; a port def, for one, cannot be `individual`)
    part def PartPlain;
    abstract part def PartAbs;
    variation part def PartVar { variant part v1; variant part v2; }
    individual part def PartInd;
    item def ItemPlain;
    abstract item def ItemAbs;
    variation item def ItemVar { variant item v1; variant item v2; }
    individual item def ItemInd;
    occurrence def OccPlain;
    abstract occurrence def OccAbs;
    variation occurrence def OccVar { variant occurrence v1; variant occurrence v2; }
    individual occurrence def OccInd;
    action def ActPlain;
    abstract action def ActAbs;
    variation action def ActVar { variant action v1; variant action v2; }
    individual action def ActInd;

    // the same, nested in a part definition
    part def Holder {
        part def PartPlain;
        abstract part def PartAbs;
        variation part def PartVar { variant part v1; variant part v2; }
        individual part def PartInd;
        item def ItemPlain;
        abstract item def ItemAbs;
        variation item def ItemVar { variant item v1; variant item v2; }
        individual item def ItemInd;
        occurrence def OccPlain;
        abstract occurrence def OccAbs;
        variation occurrence def OccVar { variant occurrence v1; variant occurrence v2; }
        individual occurrence def OccInd;
        action def ActPlain;
        abstract action def ActAbs;
        variation action def ActVar { variant action v1; variant action v2; }
        individual action def ActInd;
    }
}
