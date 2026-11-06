package B12 {
    port def P;
    connection def Link {
        end supplier : P;
        end consumer : P;
    }
    interface def Iface {
        end port supplier : P;
        end port consumer : P;
    }

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
        // named ends, end depth 0: the owner's own ports
        connection c0 : Link connect supplier ::> q to consumer ::> r;
        interface i0 : Iface connect supplier ::> q to consumer ::> r;
        // named ends, end depth 1
        connection c1 : Link connect supplier ::> x.p to consumer ::> y.p;
        interface i1 : Iface connect supplier ::> x.p to consumer ::> y.p;
        // named ends, end depth 2
        connection c2 : Link connect supplier ::> m.u1.p to consumer ::> n.u2.p;
        interface i2 : Iface connect supplier ::> m.u1.p to consumer ::> n.u2.p;
    }
    part vehicle : Vehicle;             // connectors read through a typing usage
    part def Fleet {
        part v : Vehicle;
    }
    part fleet : Fleet;                 // ... through a chain of nested usages: fleet.v
}
