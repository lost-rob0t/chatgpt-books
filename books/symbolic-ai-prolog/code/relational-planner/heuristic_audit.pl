:- module(heuristic_audit,
          [ audit_heuristic/6
          ]).

:- use_module(library(assoc),
              [ empty_assoc/1,
                get_assoc/3,
                put_assoc/4
              ]).
:- use_module(library(error), [must_be/2]).
:- use_module(cost_search, [uniform_cost_plan/5]).
:- use_module(planner,
              [ applicable/3,
                apply_instance/3,
                canonical_state/2
              ]).

%% audit_heuristic(+CostedSchemas, +Start, +Goals, +Heuristic,
%%                 +MaxStates, -Report) is det.
%
% Audit heuristic premises only after a finite reachable-state closure has been
% established within MaxStates.  A cutoff returns no admissibility/consistency
% verdict.  On a complete closure the report is:
%
%   audited(summary(StateCount, EdgeCount),
%           verdict(Admissibility, Consistency),
%           problems(Problems),
%           unreachable_goal_states(Unreachable))
%
% where Problems may contain:
%
%   inadmissible(State, H, OptimalRemainingCost)
%   inconsistent(State, Step, H, Cost, NextState, NextH)
%
% This is a finite teaching-domain checker.  It is not a proof procedure for
% arbitrary or infinite planning domains.
audit_heuristic(CostedSchemas,
                Start0,
                Goals0,
                Heuristic0,
                MaxStates,
                Report) :-
    validate_state_limit(MaxStates),
    validate_costed_schemas(CostedSchemas),
    canonical_state(Start0, Start),
    canonical_state(Goals0, Goals),
    prepare_audit_heuristic(Heuristic0, Heuristic),
    reachable_closure(CostedSchemas,
                      Start,
                      MaxStates,
                      ClosureStatus,
                      States,
                      Edges),
    length(States, StateCount),
    length(Edges, EdgeCount),
    (   ClosureStatus = cutoff(Candidate)
    ->  Report = cutoff(state_limit(MaxStates),
                         summary(StateCount, EdgeCount),
                         candidate(Candidate))
    ;   audit_states(States,
                     CostedSchemas,
                     Goals,
                     Heuristic,
                     StateProblems,
                     Unreachable),
        audit_edges(Edges, Heuristic, EdgeProblems),
        append(StateProblems, EdgeProblems, Problems),
        admissibility_verdict(Problems, Admissibility),
        consistency_verdict(Problems, Consistency),
        Report = audited(summary(StateCount, EdgeCount),
                         verdict(Admissibility, Consistency),
                         problems(Problems),
                         unreachable_goal_states(Unreachable))
    ).

reachable_closure(CostedSchemas,
                  Start,
                  MaxStates,
                  Status,
                  States,
                  Edges) :-
    closure_loop([Start],
                 [Start],
                 [],
                 CostedSchemas,
                 MaxStates,
                 Status,
                 States,
                 Edges).

closure_loop([], Seen, Edges, _, _, complete, Seen, Edges).
closure_loop([State|Frontier0],
             Seen0,
             Edges0,
             CostedSchemas,
             MaxStates,
             Status,
             Seen,
             Edges) :-
    state_edges(CostedSchemas, State, StateEdges),
    append(Edges0, StateEdges, Edges1),
    admit_edge_states(StateEdges,
                      Seen0,
                      MaxStates,
                      Seen1,
                      NewStates,
                      Admission),
    (   Admission = cutoff(Candidate)
    ->  Status = cutoff(Candidate),
        Seen = Seen1,
        Edges = Edges1
    ;   append(Frontier0, NewStates, Frontier1),
        closure_loop(Frontier1,
                     Seen1,
                     Edges1,
                     CostedSchemas,
                     MaxStates,
                     Status,
                     Seen,
                     Edges)
    ).

state_edges(CostedSchemas, State, Edges) :-
    findall(edge(State, Step, Cost, NextState),
            ( member(costed(Schema, Cost), CostedSchemas),
              applicable(Schema,
                         State,
                         instance(Id, Action, Add, Delete)),
              Step = step(Id, Action),
              apply_instance(instance(Id, Action, Add, Delete),
                             State,
                             NextState)
            ),
            Edges).

admit_edge_states([], Seen, _, Seen, [], complete).
admit_edge_states([edge(_, _, _, NextState)|Rest],
                  Seen0,
                  MaxStates,
                  Seen,
                  NewStates,
                  Status) :-
    (   memberchk(NextState, Seen0)
    ->  admit_edge_states(Rest,
                          Seen0,
                          MaxStates,
                          Seen,
                          NewStates,
                          Status)
    ;   length(Seen0, Count),
        (   Count >= MaxStates
        ->  Seen = Seen0,
            NewStates = [],
            Status = cutoff(NextState)
        ;   append(Seen0, [NextState], Seen1),
            NewStates = [NextState|MoreStates],
            admit_edge_states(Rest,
                              Seen1,
                              MaxStates,
                              Seen,
                              MoreStates,
                              Status)
        )
    ).

audit_states([], _, _, _, [], []).
audit_states([State|Rest],
             CostedSchemas,
             Goals,
             Heuristic,
             Problems,
             Unreachable) :-
    heuristic_value(Heuristic, State, H),
    uniform_cost_plan(CostedSchemas, State, Goals, Result, _),
    (   Result = found(plan(OptimalCost, _, _))
    ->  (   H =< OptimalCost
        ->  Problems = RestProblems
        ;   Problems = [inadmissible(State, H, OptimalCost)|RestProblems]
        ),
        Unreachable = RestUnreachable
    ;   Result = exhausted(_)
    ->  Problems = RestProblems,
        Unreachable = [unreachable(State, H)|RestUnreachable]
    ),
    audit_states(Rest,
                 CostedSchemas,
                 Goals,
                 Heuristic,
                 RestProblems,
                 RestUnreachable).

audit_edges([], _, []).
audit_edges([edge(State, Step, Cost, NextState)|Rest],
            Heuristic,
            Problems) :-
    heuristic_value(Heuristic, State, H),
    heuristic_value(Heuristic, NextState, NextH),
    Bound is Cost + NextH,
    (   H =< Bound
    ->  Problems = RestProblems
    ;   Problems = [inconsistent(State,
                                 Step,
                                 H,
                                 Cost,
                                 NextState,
                                 NextH)
                         |RestProblems]
    ),
    audit_edges(Rest, Heuristic, RestProblems).

admissibility_verdict(Problems, inadmissible) :-
    member(inadmissible(_, _, _), Problems),
    !.
admissibility_verdict(_, admissible_on_audited_states).

consistency_verdict(Problems, inconsistent) :-
    member(inconsistent(_, _, _, _, _, _), Problems),
    !.
consistency_verdict(_, consistent_on_audited_edges).

prepare_audit_heuristic(zero, zero) :-
    !.
prepare_audit_heuristic(table(Entries), table(Assoc)) :-
    !,
    must_be(list, Entries),
    empty_assoc(Empty),
    add_estimates(Entries, Empty, Assoc).
prepare_audit_heuristic(Term, _) :-
    throw(error(type_error(planning_heuristic, Term),
                context(heuristic_audit,
                        'Expected zero or table([estimate(State,H), ...])'))).

add_estimates([], Assoc, Assoc).
add_estimates([estimate(State0, H)|Rest], Assoc0, Assoc) :-
    !,
    canonical_state(State0, State),
    require_nonnegative_integer(heuristic_value, H),
    (   get_assoc(State, Assoc0, _)
    ->  throw(error(permission_error(insert,
                                     heuristic_estimate,
                                     State),
                    context(heuristic_audit,
                            'Duplicate heuristic state')))
    ;   put_assoc(State, Assoc0, H, Assoc1)
    ),
    add_estimates(Rest, Assoc1, Assoc).
add_estimates([Term|_], _, _) :-
    throw(error(type_error(heuristic_estimate, Term),
                context(heuristic_audit,
                        'Expected estimate(State,H)'))).

heuristic_value(zero, _, 0).
heuristic_value(table(Assoc), State, H) :-
    (   get_assoc(State, Assoc, H)
    ->  true
    ;   throw(error(existence_error(heuristic_estimate, State),
                    context(heuristic_audit,
                            'No heuristic estimate for audited reachable state')))
    ).

validate_costed_schemas(CostedSchemas) :-
    must_be(list, CostedSchemas),
    maplist(validate_costed_schema, CostedSchemas).

validate_costed_schema(costed(Schema, Cost)) :-
    !,
    validate_schema_shell(Schema),
    require_nonnegative_integer(action_cost, Cost).
validate_costed_schema(Term) :-
    throw(error(type_error(costed_planning_schema, Term),
                context(heuristic_audit,
                        'Expected costed(schema(...), Cost)'))).

validate_schema_shell(schema(Id, Action, Preconditions, Add, Delete)) :-
    !,
    must_be(atom, Id),
    require_nonvar(planning_action_template, Action),
    must_be(list, Preconditions),
    must_be(list, Add),
    must_be(list, Delete).
validate_schema_shell(Term) :-
    throw(error(type_error(planning_schema, Term),
                context(heuristic_audit,
                        'Expected schema(Id,Action,Preconditions,Add,Delete)'))).

validate_state_limit(MaxStates) :-
    (   integer(MaxStates)
    ->  (   MaxStates >= 1
        ->  true
        ;   throw(error(domain_error(positive_integer, MaxStates),
                        context(heuristic_audit, state_limit)))
        )
    ;   throw(error(type_error(integer, MaxStates),
                    context(heuristic_audit, state_limit)))
    ).

require_nonvar(_, Term) :-
    nonvar(Term),
    !.
require_nonvar(Label, _) :-
    throw(error(instantiation_error,
                context(heuristic_audit, Label))).

require_nonnegative_integer(_, Value) :-
    integer(Value),
    Value >= 0,
    !.
require_nonnegative_integer(Label, Value) :-
    (   integer(Value)
    ->  throw(error(domain_error(non_negative_integer, Value),
                    context(heuristic_audit, Label)))
    ;   throw(error(type_error(integer, Value),
                    context(heuristic_audit, Label)))
    ).
