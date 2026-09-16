:- module(relational_planner,
          [ canonical_state/2,
            goal_satisfied/2,
            applicable/3,
            apply_instance/3,
            breadth_first_plan/5
          ]).

:- use_module(library(error), [must_be/2]).
:- use_module(library(ordsets),
              [ ord_add_element/3,
                ord_memberchk/2,
                ord_subset/2,
                ord_subtract/3,
                ord_union/3
              ]).

%% canonical_state(+Facts, -State) is det.
%
% State is a ground ordered set of symbolic facts.  Requiring ground facts
% before sort/2 avoids silently making variable ordering part of state identity.
canonical_state(Facts, State) :-
    must_be(list, Facts),
    maplist(require_ground(state_fact), Facts),
    sort(Facts, State).

%% goal_satisfied(+Goals, +State) is semidet.
%
% Goals are a conjunction represented as a ground set.  This milestone does
% not interpret negation, disjunction, or arbitrary callable goals.
goal_satisfied(Goals0, State0) :-
    canonical_state(Goals0, Goals),
    canonical_state(State0, State),
    ord_subset(Goals, State).

%% applicable(+Schema, +State, -Instance) is nondet.
%
% Schema is schema(Id, Action, Preconditions, Add, Delete).  Each attempt is
% freshened before precondition matching.  The resulting action and effects
% must be ground before they can cross into state transition semantics.
applicable(Schema0, State0, Instance) :-
    validate_schema_shape(Schema0),
    canonical_state(State0, State),
    copy_term(Schema0, schema(Id, Action, Preconditions, Add0, Delete0)),
    satisfy_preconditions(Preconditions, State),
    require_ground(planning_action, Action),
    maplist(require_ground(add_effect), Add0),
    maplist(require_ground(delete_effect), Delete0),
    sort(Add0, Add),
    sort(Delete0, Delete),
    Instance = instance(Id, Action, Add, Delete).

%% apply_instance(+Instance, +State, -NextState) is det.
%
% Effects are explicit ordered-set transforms.  Facts not named by Delete are
% preserved.  Add is applied after Delete and the output remains canonical.
apply_instance(instance(Id, Action, Add0, Delete0), State0, NextState) :-
    require_ground(schema_id, Id),
    require_ground(planning_action, Action),
    canonical_state(Add0, Add),
    canonical_state(Delete0, Delete),
    canonical_state(State0, State),
    ord_subtract(State, Delete, Remaining),
    ord_union(Remaining, Add, NextState).

%% breadth_first_plan(+Schemas, +Start, +Goals, -Result, -Trace) is det.
%
% Search a finite teaching domain using breadth-first forward state-space
% search. Result is found(plan(Steps, States)) or exhausted(Goals). Trace is
% expansion diagnostics, deliberately separate from the returned plan.
breadth_first_plan(Schemas, Start0, Goals0, Result, Trace) :-
    must_be(list, Schemas),
    maplist(validate_schema_shape, Schemas),
    canonical_state(Start0, Start),
    canonical_state(Goals0, Goals),
    Initial = node(Start, [], [Start], 0),
    planning_loop(Schemas,
                  Goals,
                  [Initial],
                  [],
                  Result,
                  [],
                  ReverseTrace),
    reverse(ReverseTrace, Trace).

planning_loop(_, Goals, [], _, exhausted(Goals), Trace, Trace).
planning_loop(Schemas,
              Goals,
              [node(State, ReverseSteps, ReverseStates, Depth)|Rest],
              Closed0,
              Result,
              Trace0,
              Trace) :-
    (   ord_memberchk(State, Closed0)
    ->  planning_loop(Schemas,
                      Goals,
                      Rest,
                      Closed0,
                      Result,
                      Trace0,
                      Trace)
    ;   Trace1 = [expanded(State, Depth)|Trace0],
        (   ord_subset(Goals, State)
        ->  reverse(ReverseSteps, Steps),
            reverse(ReverseStates, States),
            Result = found(plan(Steps, States)),
            Trace = Trace1
        ;   ord_add_element(Closed0, State, Closed1),
            successor_nodes(Schemas,
                            State,
                            ReverseSteps,
                            ReverseStates,
                            Depth,
                            Closed1,
                            Children),
            append(Rest, Children, Frontier),
            planning_loop(Schemas,
                          Goals,
                          Frontier,
                          Closed1,
                          Result,
                          Trace1,
                          Trace)
        )
    ).

successor_nodes(Schemas,
                State,
                ReverseSteps,
                ReverseStates,
                Depth,
                Closed,
                Children) :-
    NextDepth is Depth + 1,
    findall(node(NextState,
                 [step(Id, Action)|ReverseSteps],
                 [NextState|ReverseStates],
                 NextDepth),
            ( member(Schema, Schemas),
              applicable(Schema,
                         State,
                         instance(Id, Action, Add, Delete)),
              apply_instance(instance(Id, Action, Add, Delete),
                             State,
                             NextState),
              NextState \== State,
              \+ ord_memberchk(NextState, Closed)
            ),
            Children).

satisfy_preconditions([], _).
satisfy_preconditions([Precondition|Rest], State) :-
    member(Precondition, State),
    satisfy_preconditions(Rest, State).

validate_schema_shape(schema(Id, Action, Preconditions, Add, Delete)) :-
    !,
    must_be(atom, Id),
    require_nonvar(planning_action_template, Action),
    must_be(list, Preconditions),
    must_be(list, Add),
    must_be(list, Delete).
validate_schema_shape(Term) :-
    throw(error(type_error(planning_schema, Term),
                context(relational_planner,
                        'Expected schema(Id,Action,Preconditions,Add,Delete)'))).

require_nonvar(_, Term) :-
    nonvar(Term),
    !.
require_nonvar(Label, _) :-
    throw(error(instantiation_error,
                context(relational_planner, Label))).

require_ground(_, Term) :-
    ground(Term),
    !.
require_ground(Label, _) :-
    throw(error(instantiation_error,
                context(relational_planner, Label))).
