package B11 {
    port def P;
    part def Unit {
        port p : P;
    }
    part def Pair {
        part u1 : Unit;
        part u2 : Unit;
    }
    part def Vehicle {
        port q : P;
        port r : P;
        part x : Unit;
        part y : Unit;
        part m : Pair;
        part n : Pair;
        // named bindings, end depth 0 / 1 / 2
        binding b0 bind q = r;
        binding b1 bind x.p = y.p;
        binding b2 bind m.u1.p = n.u2.p;
        // unnamed bindings, end depth 0 / 1 / 2 (located as the 1st/2nd/3rd unnamed binding)
        bind q = r;
        bind x.p = y.p;
        bind m.u1.p = n.u2.p;
    }
    part vehicle : Vehicle;             // bindings read through a typing usage
    part def Fleet {
        part v : Vehicle;
    }
    part fleet : Fleet;                 // ... through a chain of nested usages: fleet.v
}
