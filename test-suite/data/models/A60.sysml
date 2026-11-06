package A60 {
    private import ScalarValues::*;

    package Lib {
        part def Pump;
        attribute rate : Real;
        alias PumpAlias for Pump;
        alias rateAlias for rate;
        package Sub {
            part def Valve;
            attribute volume : Real;
        }
        private part def SecretDef;
        private attribute secretRate : Real;
        // references to the private members, from inside Lib
        part pSecret : SecretDef;
        attribute aSecret :> secretRate;
    }
    package Facade {                    // membership imports, re-exported
        public import Lib::Pump;
        public import Lib::rate;
    }
    package FacadeAll {                 // namespace import, re-exported
        public import Lib::*;
    }
    package FacadeDeep {                // recursive import, re-exported
        public import Lib::**;
    }
    package Hidden {                    // private import: visible inside only
        private import Lib::*;
        part pUse : Pump;
        attribute aUse :> rate;
    }
    part def Base {                     // protected members: visible to specializations only
        protected part def ProtDef;
        protected attribute protRate : Real;
    }
    part def Derived :> Base {
        part pUse : ProtDef;
        attribute aUse :> protRate;
    }
    package Client {                    // references through each public path
        part pOwn : Lib::Pump;
        attribute aOwn :> Lib::rate;
        part pAlias : Lib::PumpAlias;
        attribute aAlias :> Lib::rateAlias;
        part pMem : Facade::Pump;
        attribute aMem :> Facade::rate;
        part pNs : FacadeAll::Pump;
        attribute aNs :> FacadeAll::rate;
        part pRec : FacadeDeep::Valve;
        attribute aRec :> FacadeDeep::volume;
    }
}
