package A02 {
    // definitions specializing each other, owned by a package
    part def Base {
        part a;
        attribute x;
    }
    part def Mid :> Base {             // single specialization
        part b;
    }
    part def Leaf :> Mid {             // two levels, with a redefinition
        part c;
        attribute :>> x;
    }
    part def Other {
        part o;
    }
    part def Multi :> Base, Other {    // multiple generals
        part m;
    }
    abstract part def AbsBase {
        part ab;
    }
    part def FromAbs :> AbsBase {      // abstract general
        part f;
    }

    // the same set in a nested package
    package Far {
        part def Base {
            part a;
            attribute x;
        }
        part def Mid :> Base {             // single specialization
            part b;
        }
        part def Leaf :> Mid {             // two levels, with a redefinition
            part c;
            attribute :>> x;
        }
        part def Other {
            part o;
        }
        part def Multi :> Base, Other {    // multiple generals
            part m;
        }
        abstract part def AbsBase {
            part ab;
        }
        part def FromAbs :> AbsBase {      // abstract general
            part f;
        }
    }
}
