package B10 {
    port def P;
    connection def Link {
        end a : P;
        end b : P;
    }
    interface def Iface {
        end port a : P;
        end port b : P;
    }
    connection def SubLink :> Link;     // inherits the ends a, b
    interface def SubIface :> Iface;

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
        // end depth 0: the ends are the owner's own ports
        connection c0 : Link connect q to r;
        interface i0 : Iface connect q to r;
        // end depth 1: one level of nesting (a feature chain of two)
        connection c1 : Link connect x.p to y.p;
        interface i1 : Iface connect x.p to y.p;
        // end depth 2: two levels of nesting (a feature chain of three)
        connection c2 : Link connect m.u1.p to n.u2.p;
        interface i2 : Iface connect m.u1.p to n.u2.p;
    }
    part vehicle : Vehicle;             // connectors read through a typing usage
    part def Fleet {
        part v : Vehicle;
    }
    part fleet : Fleet;                 // ... through a chain of nested usages: fleet.v
}
