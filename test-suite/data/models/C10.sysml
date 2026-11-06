package C10 {
    private import ScalarValues::*;

    port def PowerPort {
        out attribute power : Real;
    }
    action def Consume {
        in pLiteral : Real;
        in pRef : Real;
        in pChain : Real;
        in pOp : Real;
        in pNone : Real;            // never given a value
        out heat : Real;
        inout mode : Real;
    }
    action def SubConsume :> Consume;   // inherits the parameters

    part def Motor {
        port powerPort : PowerPort;
        attribute level : Real = 1.0;
        perform action consume : Consume {
            in pLiteral = 0.5;                      // literal
            in pRef = level;                        // feature reference
            in pChain = powerPort.power;            // feature chain
            in pOp = powerPort.power * 2.0;         // operator expression
        }
        action boost : Consume {
            in pLiteral = 0.5;
            in pRef = level;
            in pChain = powerPort.power;
            in pOp = powerPort.power * 2.0;
        }
    }
    part def SubMotor :> Motor;

    part motor : Motor;             // actions read through a typing usage
    part subMotor : SubMotor;       // ... through a usage of a specialized def
}
