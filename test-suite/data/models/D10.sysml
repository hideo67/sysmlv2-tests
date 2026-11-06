package D10 {
    private import ScalarValues::*;

    metadata def FailureMode {
        attribute severity : Integer;
    }
    part def Motor;

    // on a definition: prefix, body, and a separate `about` annotation
    #FailureMode part def PumpP;
    part def PumpB {
        @FailureMode { severity = 3; }
    }
    part def PumpA;
    metadata pumpA_fm : FailureMode about PumpA { severity = 2; }

    // on part usages
    part def Pump {
        #FailureMode part motorP : Motor;
        part motorB : Motor {
            @FailureMode { severity = 3; }
        }
        part motorA : Motor;
    }
    metadata motorA_fm : FailureMode about Pump::motorA { severity = 2; }
    part pump : Pump;               // the usages read through a typing usage

    // on states
    state def PumpStates {
        #FailureMode state overheatedP;
        state overheatedB {
            @FailureMode { severity = 3; }
        }
        state overheatedA;
    }
    metadata overheatedA_fm : FailureMode about PumpStates::overheatedA { severity = 2; }

    // on action parameters
    action def PumpFluid {
        in #FailureMode pressureP : Real;
        in pressureB : Real {
            @FailureMode { severity = 3; }
        }
        in pressureA : Real;
    }
    metadata pressureA_fm : FailureMode about PumpFluid::pressureA { severity = 2; }
}
