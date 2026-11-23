package C21Lib {
    // C21's constructor of a library type, in a model of its own (see gen_c21.py):
    // an MDK that rejects it loses only these cases
    private import ISQ::LengthValue;
    private import ShapeItems::Triangle;    // its first owned features: length, width, xoffset

    part def Src {
        attribute l : LengthValue;
        attribute w : LengthValue;
        attribute x : LengthValue;
    }

    // in an action def body
    action def Emit {
        in src : Src;
        item shape = new Triangle(src.l, src.w, src.x);
    }

    // nested in an action usage owned by a part def
    part def Emitter {
        part src : Src;
        action emit {
            item shape = new Triangle(src.l, src.w, src.x);
        }
    }
    part emitter : Emitter;     // read through a typing usage: emitter.emit
}
