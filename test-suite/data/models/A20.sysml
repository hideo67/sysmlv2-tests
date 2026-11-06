package A20 {
    private import ScalarValues::*;

    // attributes owned by a package
    attribute plain : Real[1];
    attribute bound : Real[1] = 1.5;
    attribute dflt : Real[1] default 2.5;
    attribute multi : Integer[2..4];

    part def Vehicle {
        attribute plain : Real[1];              // no value
        attribute bound : Real[1] = 1.5;        // bound value
        attribute dflt : Real[1] default 2.5;   // default value
        attribute multi : Integer[2..4];        // multiplicity range
    }
    part def Truck :> Vehicle;

    part vehicle : Vehicle;          // read Vehicle's attributes through a typing usage
    part truck : Truck;              // ... through a usage of a specialized def
    part tuned : Vehicle {           // ... redefined in the usage
        attribute :>> plain = 3.5;
        attribute :>> bound;              // a bound value cannot be overridden
        attribute :>> dflt = 5.5;
        attribute :>> multi : Integer[3];
    }
}
