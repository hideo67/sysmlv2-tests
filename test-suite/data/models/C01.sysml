package C01 {
    private import ScalarValues::*;
    part def Thing;

    // one behavioral definition of each kind
    action def Act {
        in x : Real;
        out y : Real;
    }
    state def St {
        in x : Real;
    }
    calc def Calc {
        in x : Real;
        return r : Real;
    }
    constraint def Cons {
        in x : Real;
        x > 0
    }
    requirement def Req {
        subject s : Thing;
        in x : Real;
    }
    use case def UC {
        subject s : Thing;
    }
    analysis def An {
        subject s : Thing;
        return r : Real;
    }
    verification def Ver {
        subject s : Thing;
    }

    // a specializing definition of each, inheriting its parameters
    action def SubAct :> Act;
    state def SubSt :> St;
    calc def SubCalc :> Calc;
    constraint def SubCons :> Cons;
    requirement def SubReq :> Req;
    use case def SubUC :> UC;
    analysis def SubAn :> An;
    verification def SubVer :> Ver;
}
