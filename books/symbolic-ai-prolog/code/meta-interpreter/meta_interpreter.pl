:- module(symbolic_meta_interpreter,
          [ prove/3,
            prove_guarded/4,
            search_report/4,
            proof_rule_ids/2
          ]).

:- use_module(library(error), [must_be/2]).

%% prove(+Program, ?Goal, -Proof) is nondet.
%
%  Interpret Goal against a closed rule-as-data Program.  Program is a list
%  of rule(Id, Head, Body) terms.  true, conjunction, and either/2 are the
%  only control forms owned by this milestone; every other goal must be
%  justified by a rule in Program.
prove(Program, Goal, Proof) :-
    must_be(list, Program),
    prove_goal(Program, Goal, Proof).

prove_goal(_, true, true) :-
    !.
prove_goal(Program, (Left, Right), and(LeftProof, RightProof)) :-
    !,
    prove_goal(Program, Left, LeftProof),
    prove_goal(Program, Right, RightProof).
prove_goal(Program, either(Left, Right), Proof) :-
    !,
    (   prove_goal(Program, Left, LeftProof),
        Proof = choice(left, LeftProof)
    ;   prove_goal(Program, Right, RightProof),
        Proof = choice(right, RightProof)
    ).
prove_goal(Program, Goal, Proof) :-
    select_rule(Program, Goal, Id, Body),
    (   Body == true
    ->  Proof = fact(Id, Goal)
    ;   prove_goal(Program, Body, BodyProof),
        Proof = step(Id, Goal, BodyProof)
    ).

%% prove_guarded(+Program, ?Goal, +RuleBudget, -Outcome) is nondet.
%
%  As prove/3, but bound interpreted rule selections and reject a variant of
%  a goal already present on the current proof path.  RuleBudget counts only
%  object-language rule selections; it is deliberately not SWI-Prolog's
%  internal recursion depth or inference count.  Each either/2 alternative
%  starts from the same incoming budget because alternatives are different
%  search branches, not sequential work on one branch.
%
%  Outcome is one of:
%    proved(Proof)
%    cycle(Goal)
%    exhausted(Goal)
%
%  Logical failure remains ordinary predicate failure.  Alternative rules
%  and either/2 branches remain available on backtracking.
prove_guarded(Program, Goal, RuleBudget, Outcome) :-
    must_be(list, Program),
    must_be(nonneg, RuleBudget),
    guarded_goal(Program, Goal, [], RuleBudget, _, Outcome).

guarded_goal(_, true, _, Budget, Budget, proved(true)) :-
    !.
guarded_goal(Program,
             (Left, Right),
             Seen,
             Budget0,
             Budget,
             Outcome) :-
    !,
    guarded_goal(Program,
                 Left,
                 Seen,
                 Budget0,
                 Budget1,
                 LeftOutcome),
    continue_conjunction(LeftOutcome,
                         Program,
                         Right,
                         Seen,
                         Budget1,
                         Budget,
                         Outcome).
guarded_goal(Program,
             either(Left, Right),
             Seen,
             Budget0,
             Budget,
             Outcome) :-
    !,
    (   guarded_goal(Program,
                     Left,
                     Seen,
                     Budget0,
                     Budget,
                     LeftOutcome),
        wrap_choice_outcome(left, LeftOutcome, Outcome)
    ;   guarded_goal(Program,
                     Right,
                     Seen,
                     Budget0,
                     Budget,
                     RightOutcome),
        wrap_choice_outcome(right, RightOutcome, Outcome)
    ).
guarded_goal(_, Goal, Seen, Budget, Budget, cycle(Goal)) :-
    seen_variant(Goal, Seen),
    !.
guarded_goal(_, Goal, _, 0, 0, exhausted(Goal)) :-
    !.
guarded_goal(Program, Goal, Seen, Budget0, Budget, Outcome) :-
    Budget0 > 0,
    select_rule(Program, Goal, Id, Body),
    Budget1 is Budget0 - 1,
    (   Body == true
    ->  Budget = Budget1,
        Outcome = proved(fact(Id, Goal))
    ;   guarded_goal(Program,
                     Body,
                     [Goal|Seen],
                     Budget1,
                     Budget,
                     BodyOutcome),
        wrap_guarded_outcome(BodyOutcome, Id, Goal, Outcome)
    ).

continue_conjunction(proved(LeftProof),
                     Program,
                     Right,
                     Seen,
                     Budget0,
                     Budget,
                     Outcome) :-
    guarded_goal(Program,
                 Right,
                 Seen,
                 Budget0,
                 Budget,
                 RightOutcome),
    combine_conjunction_outcome(RightOutcome, LeftProof, Outcome).
continue_conjunction(cycle(Goal),
                     _,
                     _,
                     _,
                     Budget,
                     Budget,
                     cycle(Goal)).
continue_conjunction(exhausted(Goal),
                     _,
                     _,
                     _,
                     Budget,
                     Budget,
                     exhausted(Goal)).

combine_conjunction_outcome(proved(RightProof),
                            LeftProof,
                            proved(and(LeftProof, RightProof))).
combine_conjunction_outcome(cycle(Goal), _, cycle(Goal)).
combine_conjunction_outcome(exhausted(Goal), _, exhausted(Goal)).

wrap_choice_outcome(Side,
                    proved(Proof),
                    proved(choice(Side, Proof))).
wrap_choice_outcome(_, cycle(Goal), cycle(Goal)).
wrap_choice_outcome(_, exhausted(Goal), exhausted(Goal)).

wrap_guarded_outcome(proved(BodyProof),
                     Id,
                     Goal,
                     proved(step(Id, Goal, BodyProof))).
wrap_guarded_outcome(cycle(CycleGoal), _, _, cycle(CycleGoal)).
wrap_guarded_outcome(exhausted(ExhaustedGoal),
                     _,
                     _,
                     exhausted(ExhaustedGoal)).

%% search_report(+Program, +Goal, +RuleBudget, -Report) is det.
%
%  Produce a bounded object-level diagnostic for one *ground ordinary goal*.
%  This is intentionally not SWI-Prolog's debugger trace.  It reports only
%  stored rules whose freshened heads unify with Goal, preserving program
%  order, and classifies the guarded outcomes of each matching rule body.
%
%  Report is one of:
%    blocked(exhausted(Goal))
%    search(Goal, Attempts)
%
%  Each attempt is:
%    attempt(Id, failed)
%    attempt(Id, outcomes(Outcomes))
%
%  where Outcomes use the same proved/cycle/exhausted vocabulary as
%  prove_guarded/4.  A failed attempt means the selected rule head unified but
%  its body produced no guarded outcome.  Rules whose heads do not unify are
%  outside this deliberately small report.
search_report(Program, Goal, RuleBudget, Report) :-
    must_be(list, Program),
    must_be(nonneg, RuleBudget),
    require_report_goal(Goal),
    (   RuleBudget =:= 0
    ->  Report = blocked(exhausted(Goal))
    ;   findall(Attempt,
                rule_attempt(Program, Goal, RuleBudget, Attempt),
                Attempts),
        Report = search(Goal, Attempts)
    ).

require_report_goal(Goal) :-
    (   ground(Goal)
    ->  true
    ;   throw(error(instantiation_error,
                    context(search_report/4,
                            'Goal must be ground')))
    ),
    (   object_control_goal(Goal)
    ->  throw(error(domain_error(object_rule_goal, Goal),
                    context(search_report/4,
                            'Goal must be an ordinary object goal')))
    ;   true
    ).

object_control_goal(true).
object_control_goal((_, _)).
object_control_goal(either(_, _)).

rule_attempt(Program, Goal, RuleBudget, attempt(Id, Result)) :-
    select_rule(Program, Goal, Id, Body),
    BodyBudget is RuleBudget - 1,
    (   Body == true
    ->  Result = outcomes([proved(fact(Id, Goal))])
    ;   findall(Outcome,
                ( guarded_goal(Program,
                               Body,
                               [Goal],
                               BodyBudget,
                               _,
                               BodyOutcome),
                  wrap_guarded_outcome(BodyOutcome,
                                       Id,
                                       Goal,
                                       Outcome)
                ),
                Outcomes),
        classify_attempt(Outcomes, Result)
    ).

classify_attempt([], failed).
classify_attempt([Outcome|Outcomes], outcomes([Outcome|Outcomes])).

select_rule(Program, Goal, Id, Body) :-
    member(RuleTemplate, Program),
    copy_term(RuleTemplate, rule(Id, Head, Body)),
    Head = Goal.

seen_variant(Goal, [Seen|_]) :-
    Goal =@= Seen,
    !.
seen_variant(Goal, [_|Rest]) :-
    seen_variant(Goal, Rest).

%% proof_rule_ids(+Proof, -RuleIds) is det.
%
%  Return the rule identifiers used by one proof in preorder.  Repeated IDs
%  are retained because repeated rule applications are provenance, not noise.
%  Control nodes such as conjunction and choice do not invent rule IDs.
proof_rule_ids(true, []).
proof_rule_ids(fact(Id, _), [Id]).
proof_rule_ids(step(Id, _, BodyProof), [Id|Ids]) :-
    proof_rule_ids(BodyProof, Ids).
proof_rule_ids(and(LeftProof, RightProof), Ids) :-
    proof_rule_ids(LeftProof, LeftIds),
    proof_rule_ids(RightProof, RightIds),
    append(LeftIds, RightIds, Ids).
proof_rule_ids(choice(_, Proof), Ids) :-
    proof_rule_ids(Proof, Ids).
