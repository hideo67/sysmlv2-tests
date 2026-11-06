package E10 {
    private import ScalarValues::*;
    private import ISQ::*;
    private import SI::*;

    part def Engine {
        attribute power : Real default 100.0;    // defaults, so that `tuned` may override them
    }
    part def Vehicle {
        part engine : Engine;
        attribute lit : Real default 2.5;                     // literal
        attribute arith : Real = 2 * 3 + 0.5;               // arithmetic
        attribute refd : Real = lit;                        // feature reference
        attribute chain : Real = engine.power;              // feature chain
        attribute cond : Real = if lit > 1.0 ? 1.0 else 0.0;   // conditional
        attribute flag : Boolean = lit > 2.0;               // comparison
        attribute label : String = "pump";                  // string
        attribute mass : MassValue = 1500.0 [kg];           // quantity with a unit
    }
    part vehicle : Vehicle;                     // evaluated in a typing usage
    part tuned : Vehicle {                      // evaluated where redefinitions change the inputs
        attribute :>> lit = 0.5;
        part :>> engine {
            attribute :>> power = 200.0;
        }
    }
}
