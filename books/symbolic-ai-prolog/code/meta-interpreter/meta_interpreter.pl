:- module(symbolic_meta_interpreter,
          [ prove/3
          ]).

%% prove(+Program, ?Goal, -Proof) is nondet.
%
%  Deliberately minimal first-stage interpreter used to establish the
%  Project 1 regression baseline.  Program is a list of rule(Id,Head,Body)
%  terms.  The next implementation step hardens rule freshness and adds the
%  bounded/cycle-aware runner required by issue #24.
prove(Program, Goal, Proof) :-
    prove_goal(Program, Goal, Proof).

prove_goal(_, true, true) :-
    !.
prove_goal(Program, (Left, Right), and(LeftProof, RightProof)) :-
    !,
    prove_goal(Program, Left, LeftProof),
    prove_goal(Program, Right, RightProof).
prove_goal(Program, Goal, Proof) :-
    member(rule(Id, Goal, Body), Program),
    (   Body == true
    ->  Proof = fact(Id, Goal)
    ;   prove_goal(Program, Body, BodyProof),
        Proof = step(Id, Goal, BodyProof)
    ).
