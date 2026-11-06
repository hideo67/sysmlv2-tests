package C30Accept {
    // C30's accept-action state, in a model of its own (see gen_c30.py)
    attribute def Sig;
    port def SigPort;

    state def Ctl {
        port p : SigPort;
        state sAccept {
            entry accept a1 : Sig via p;
            do accept a2 : Sig via p;
            exit accept a3 : Sig via p;
        }
    }
    part def Device {
        exhibit state ex : Ctl;
    }
    part device : Device;
}
