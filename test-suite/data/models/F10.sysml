package F10 {
    private import ScalarValues::*;

    port def FuelPort;
    part def Valve;
    part def Tank {
        attribute capacity : Real default 50.0;
        port fuelOut : FuelPort;
        part valves : Valve[2];
    }
    part def Engine {
        port fuelIn : FuelPort;
    }
    part def Powertrain {
        part tank : Tank;
        part engine : Engine;
    }
    part def Drive {
        part powertrain : Powertrain;
    }
    part def Vehicle {
        part engine : Engine;
        part tank : Tank;                               // path depth 1: tank
        part powertrain : Powertrain {                  // path depth 2: powertrain.tank, capacity redefined
            part :>> tank {
                attribute :>> capacity = 60.0;
            }
        }
        part drive : Drive;                             // path depth 3: drive.powertrain.tank
        connection c1 connect src ::> tank.fuelOut to dst ::> engine.fuelIn;
        connection c2 connect src ::> powertrain.tank.fuelOut to dst ::> engine.fuelIn;
        connection c3 connect src ::> drive.powertrain.tank.fuelOut to dst ::> engine.fuelIn;
    }
    part vehicle : Vehicle;
}
