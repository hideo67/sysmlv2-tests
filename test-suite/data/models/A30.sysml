package A30 {
    private import ScalarValues::*;

    port def CmdPort {
        out attribute cmd : Integer;    // flows out of a CmdPort
        in attribute ack : Boolean;     // flows into a CmdPort
    }
    part def Device {
        port pOut : CmdPort;            // ordinary typing
        port pIn : ~CmdPort;            // conjugated typing: cmd flows in, ack flows out
    }
    part def SubDevice :> Device;
    part def Rack {
        part slot : Device;
    }

    part device : Device;               // ports read through a typing usage
    part sub : SubDevice;               // ... through a usage of a specialized def
    part rack : Rack;                   // ... through a chain of nested usages: rack.slot
}
