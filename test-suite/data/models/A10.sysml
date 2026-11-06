package A10 {
    part def Engine;
    part def Person;
    part def Car {
        part engine : Engine;       // owned (composite) part
        ref part driver : Person;   // reference part
        part : Engine;              // unnamed part
    }
    part def SportsCar :> Car;      // specializes Car, inherits its members
    part car : Car;                 // owned part in a package, typed by Car
    part sportsCar : SportsCar;     // usage of the specialized def
    ref part owner : Person;        // reference part in a package
    part : Car;                     // unnamed part in a package
}
