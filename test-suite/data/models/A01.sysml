package A01 {
    // one definition of each structural kind, with a short name, owned by a package
    part def <PD> PartD;
    item def <ID> ItemD;
    attribute def <AD> AttrD;
    port def <POD> PortD;
    connection def <CD> ConnD { end part a; end part b; }
    interface def <IFD> IfaceD { end port a; end port b; }
    allocation def <ALD> AllocD;
    enum def <ED> EnumD { enum a; enum b; }
    occurrence def <OD> OccD;
    metadata def <MD> MetaD;

    // the same, nested in a part definition
    part def Holder {
        part def <PD> PartD;
        item def <ID> ItemD;
        attribute def <AD> AttrD;
        port def <POD> PortD;
        connection def <CD> ConnD { end part a; end part b; }
        interface def <IFD> IfaceD { end port a; end port b; }
        allocation def <ALD> AllocD;
        enum def <ED> EnumD { enum a; enum b; }
        occurrence def <OD> OccD;
        metadata def <MD> MetaD;
    }

    // the same, in a nested package
    package Inner {
        part def <PD> PartD;
        item def <ID> ItemD;
        attribute def <AD> AttrD;
        port def <POD> PortD;
        connection def <CD> ConnD { end part a; end part b; }
        interface def <IFD> IfaceD { end port a; end port b; }
        allocation def <ALD> AllocD;
        enum def <ED> EnumD { enum a; enum b; }
        occurrence def <OD> OccD;
        metadata def <MD> MetaD;
    }
}
