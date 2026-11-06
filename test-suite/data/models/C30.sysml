package C30 {
    private import ScalarValues::*;

    attribute def Sig;
    port def SigPort;
    action def Notify;

    state def Ctl {
        ref sig : Sig;
        port p : SigPort;
        attribute count : Integer;
        action onEntry : Notify;
        action onDo : Notify;
        action onExit : Notify;

        // entry / do / exit actions of each kind
        state sSend {
            entry send sig via p;
            do send sig via p;
            exit send sig via p;
        }
        // the accept-action state is in C30-accept.sysml, so that an MDK rejecting it
        // does not lose the rest of this model
        state sAssign {
            entry assign count := 1;
            do assign count := 2;
            exit assign count := 3;
        }
        state sPerform {
            entry onEntry;              // a performed action: no `perform` keyword here (StateActionUsage)
            do onDo;
            exit onExit;
        }

        // structure: sequential substates, parallel regions
        state seq {
            state s1;
            state s2;
        }
        state par parallel {
            state r1;
            state r2;
        }

        // transitions: with trigger, guard and effect; and a bare one
        transition t1 first sSend accept s : Sig via p if count > 0 do assign count := 0 then sAssign;
        transition t2 first sAssign then sPerform;
    }

    part def Device {
        exhibit state ex : Ctl;         // the states read through an exhibited state usage
    }
    part device : Device;               // ... and through a typing usage of the part def
}
