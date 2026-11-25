package C21 {
    private import ScalarValues::*;

    attribute def Sig {
        attribute level : Real;
    }
    port def SigPort;
    part def Src {
        attribute v : Real;
    }
    item def Message;
    item def Command :> Message;

    // constructors in an action def body
    action def Emit {
        in sp : SigPort;
        in src : Src;
        in gain : Real;

        action sendNone send new Sig() via sp;          // no argument
        action sendRef send new Sig(gain) via sp;       // a feature reference argument
        action sendChain send new Sig(src.v) via sp;    // a feature chain argument
        attribute sigValue : Sig = new Sig(src.v);      // a constructor as a feature value

        // added later: the type operators, whose type operand is the result (cast, all) or an
        // input (istype) by the grammar (TypeResultMember / TypeReferenceMember)
        in item original : Message;
        item narrowed : Command = original as Command;              // a cast
        item allCommands : Command[0..*] = all Command;             // all instances of a type
        attribute tested : Boolean = original istype Command;       // a classification test
    }

    // the same constructors, nested in an action usage owned by a part def
    part def Emitter {
        port sp : SigPort;
        part src : Src;
        attribute gain : Real;
        action emit {
            action sendNone send new Sig() via sp;
            action sendRef send new Sig(gain) via sp;
            action sendChain send new Sig(src.v) via sp;
            attribute sigValue : Sig = new Sig(src.v);
            item narrowed : Command = original as Command;
            item allCommands : Command[0..*] = all Command;
            attribute tested : Boolean = original istype Command;
        }
        item original : Message;
    }
    part emitter : Emitter;     // read through a typing usage: emitter.emit
}
