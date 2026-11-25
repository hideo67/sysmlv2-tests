package C31 {
    action def Run;
    state def Modes;

    // targets of the references written directly in the part def: a perform or exhibit by
    // reference takes the referenced feature's name, so a target in the part def itself would
    // clash with it
    action shared : Run;
    state sharedModes : Modes;

    part def Machine {
        action real : Run;

        perform shared;                  // perform by reference          -> C31::shared
        perform action own : Run;        // perform, declared             -> itself
        exhibit sharedModes;             // exhibit by reference          -> C31::sharedModes
        exhibit state modes {            // exhibit, declared             -> itself
            state normal {
                perform real;            // perform by reference, in a state -> C31::Machine::real
                do action work;          // do action, declared (a PerformActionUsage) -> itself
            }
            state idle {
                entry real;              // entry action by reference     -> C31::Machine::real
            }
        }
    }
    part def SubMachine :> Machine;

    part machine : Machine;              // read through a typing usage
    part subMachine : SubMachine;        // ... through a usage of a specialized def
}
