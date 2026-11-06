package D20 {
    // on packages: documentation, a body comment, a comment about it, a textual representation
    package PDoc {
        doc /* package doc */
    }
    package PCom {
        comment /* package comment */
    }
    package PAbout;
    comment aboutPAbout about PAbout /* package about */
    package PRep {
        rep language "text" /* package rep */
    }

    // on part definitions
    part def DefDoc {
        doc /* def doc */
    }
    part def DefCom {
        comment /* def comment */
    }
    part def DefAbout;
    comment aboutDefAbout about DefAbout /* def about */
    part def DefRep {
        rep language "text" /* def rep */
    }

    // on part usages
    part def Holder {
        part uDoc {
            doc /* usage doc */
        }
        part uCom {
            comment /* usage comment */
        }
        part uAbout;
        part uRep {
            rep language "text" /* usage rep */
        }
    }
    comment aboutUAbout about Holder::uAbout /* usage about */
    part holder : Holder;               // the usages read through a typing usage
}
