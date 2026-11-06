package A50 {
    private import ScalarValues::*;

    metadata def M;
    part def Unit {
        out item o;
        in item i;
    }

    // unnamed members of a package (in declaration order: connect before flow)
    part u1 : Unit;
    part u2 : Unit;
    part : Unit;
    attribute : Real;
    bind u1.o = u2.o;
    connect u1 to u2;
    flow from u1.o to u2.i;
    @M;

    // unnamed members of a part definition
    part def Holder {
        part x : Unit;
        part y : Unit;
        part : Unit;
        attribute : Real;
        bind x.o = y.o;
        connect x to y;
        flow from x.o to y.i;
        @M;
    }
    part holder : Holder;           // the part def's unnamed members read through a typing usage
}
