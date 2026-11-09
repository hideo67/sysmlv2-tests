package B13 {
    attribute def Sig;
    port def P;

    // ---- successions: one owner per form, so an unnamed succession is the 1st or 2nd of its owner
    action def Named {                      // a named succession
        action a1;
        action a2;
        succession s first a1 then a2;
    }
    action def Unnamed {                    // an unnamed succession
        action a1;
        action a2;
        first a1 then a2;
    }
    action def Shorthand {                  // the `then` shorthand, from the preceding `first`
        action a1;
        action a2;
        first a1;
        then a2;
    }
    action def NodeEnds {                   // ends at unnamed action nodes
        action a1;
        action a2;
        first a1;
        then accept Sig;                    // 1st unnamed succession: a1 -> the accept node
        then action a3;                     // 2nd unnamed succession: the accept node -> a3
    }
    action def Guarded {                    // a guarded succession, a TransitionUsage
        action a1;
        decide d;
        succession g first d if true then a1;
    }
    state def Machine {                     // a state transition, a TransitionUsage
        state s1;
        state s2;
        transition t first s1 accept Sig then s2;
    }

    // ---- connectors whose ends are declared in their body
    connection def C {
        end e1;
        end e2;
    }
    interface def I {
        end port i1 : P;
        end port i2 : P;
    }
    part def Sys {
        part d1;
        part d2;
        port p1 : P;
        port p2 : P;
        connection k1 : C {                 // ends redefining the def's ends
            end :>> e1 ::> d1;
            end :>> e2 ::> d2;
        }
        connection k2 {                     // own ends
            end f1 ::> d1;
            end f2 ::> d2;
        }
        interface j1 : I {
            end :>> i1 ::> p1;
            end :>> i2 ::> p2;
        }
        interface j2 {
            end port g1 ::> p1;
            end port g2 ::> p2;
        }
    }

    // read through a typing usage
    action named : Named;
    action unnamed : Unnamed;
    action shorthand : Shorthand;
    action nodeEnds : NodeEnds;
    action guarded : Guarded;
    state machine : Machine;
    part sys : Sys;

    // read through a chain of nested usages: plant.<usage>
    part def Plant {
        action named : Named;
        action unnamed : Unnamed;
        action shorthand : Shorthand;
        action nodeEnds : NodeEnds;
        action guarded : Guarded;
        state machine : Machine;
        part sys : Sys;
    }
    part plant : Plant;
}
