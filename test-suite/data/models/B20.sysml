package B20 {
    item def Fuel;
    item def Sig;

    part def Tank {
        out item fuelOut : Fuel;
    }
    part def Engine {
        in item fuelIn : Fuel;
    }
    part def Module {
        part tank : Tank;
        part engine : Engine;
    }
    part def Vehicle {
        // a flow end must name a participant with dot notation, so there is no end depth 0
        part tank : Tank;                   // end depth 1
        part engine : Engine;
        part m : Module;                    // end depth 2
        part n : Module;

        flow f1 of Fuel from tank.fuelOut to engine.fuelIn;
        flow f2 of Fuel from m.tank.fuelOut to n.engine.fuelIn;
        succession flow s1 of Fuel from tank.fuelOut to engine.fuelIn;
        succession flow s2 of Fuel from m.tank.fuelOut to n.engine.fuelIn;
        message msg of Sig from tank to engine;
    }
    part vehicle : Vehicle;                 // flows read through a typing usage
    part def Fleet {
        part v : Vehicle;
    }
    part fleet : Fleet;                     // ... through a chain of nested usages: fleet.v
}
