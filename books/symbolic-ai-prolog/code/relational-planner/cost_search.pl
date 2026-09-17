:- module(cost_search,
          [ uniform_cost_plan/5,
            a_star_plan/6
          ]).

:- use_module(library(assoc),
              [ empty_assoc/1,
                get_assoc/3,
                put_assoc/4
              ]).
:- use_module(library(error), [must_be/2]).
:- use_module(library(heaps),
              [ add_to_heap/4,
                empty_heap/1,
                get_from_heap/4
              ]).
:- use_module(planner,
              [ applicable/3,
                apply_instance/3,
                canonical_state/2,
                goal_satisfied/2
              ]).

%% uniform_cost_plan(+CostedSchemas, +Start, +Goals, -Result, -Trace) is det.
%
% Search by accumulated action cost.  Costs are explicit non-negative integers
% attached to inert schema data as costed(Schema, Cost).  Result is either
% found(plan(Cost, Steps, States)) or exhausted(Goals).
uniform_cost_plan(CostedSchemas, Start, Goals, Result, Trace) :-
    cost_search(CostedSchemas, Start, Goals, zero, Result, Trace).

%% a_star_plan(+CostedSchemas, +Start, +Goals, +Heuristic, -Result, -Trace) is det.
%
% Heuristic is closed data: either zero or table([estimate(State, H), ...]).
% No caller-supplied term is executed as a Prolog goal.
a_star_plan(CostedSchemas, Start, Goals, Heuristic0, Result, Trace) :-
    prepare_heuristic(Heuristic0, Heuristic),
    cost_search(CostedSchemas, Start, Goals, Heuristic, Result, Trace).

cost_search(CostedSchemas0, Start0, Goals0, Heuristic, Result, Trace) :-
    validate_costed_schemas(CostedSchemas0),
    canonical_state(Start0, Start),
    canonical_state(Goals0, Goals),
    heuristic_value(Heuristic, Start, H0),
    empty_heap(Heap0),
    add_to_heap(Heap0,
                priority(H0, 0),
                node(Start, [], [Start], 0, 0),
                Heap1),
    empty_assoc(Best0),
    put_assoc(Start, Best0, 0, Best1),
    best_first_loop(CostedSchemas0,
                    Goals,
                    Heuristic,
                    Heap1,
                    Best1,
                    1,
                    Result,
                    [],
                    ReverseTrace),
    reverse(ReverseTrace, Trace).

best_first_loop(_, Goals, _, Heap, _, _, exhausted(Goals), Trace, Trace) :-
    \+ get_from_heap(Heap, _, _, _),
    !.
best_first_loop(CostedSchemas,
                Goals,
                Heuristic,
                Heap0,
                Best0,
                Sequence0,
                Result,
                Trace0,
                Trace) :-
    get_from_heap(Heap0,
                  priority(F, _),
                  node(State, ReverseSteps, ReverseStates, G, Depth),
                  Heap1),
    get_assoc(State, Best0, BestG),
    (   G > BestG
    ->  Trace1 = [stale(State, G, BestG)|Trace0],
        best_first_loop(CostedSchemas,
                        Goals,
                        Heuristic,
                        Heap1,
                        Best0,
                        Sequence0,
                        Result,
                        Trace1,
                        Trace)
    ;   Trace1 = [expanded(State, G, F, Depth)|Trace0],
        (   goal_satisfied(Goals, State)
        ->  reverse(ReverseSteps, Steps),
            reverse(ReverseStates, States),
            Result = found(plan(G, Steps, States)),
            Trace = Trace1
        ;   expand_costed_schemas(CostedSchemas,
                                  State,
                                  ReverseSteps,
                                  ReverseStates,
                                  G,
                                  Depth,
                                  Heuristic,
                                  Heap1,
                                  Best0,
                                  Sequence0,
                                  Trace1,
                                  Heap2,
                                  Best1,
                                  Sequence1,
                                  Trace2),
            best_first_loop(CostedSchemas,
                            Goals,
                            Heuristic,
                            Heap2,
                            Best1,
                            Sequence1,
                            Result,
                            Trace2,
                            Trace)
        )
    ).

expand_costed_schemas([], _, _, _, _, _, _, Heap, Best, Sequence, Trace,
                      Heap, Best, Sequence, Trace).
expand_costed_schemas([costed(Schema, Cost)|Rest],
                      State,
                      ReverseSteps,
                      ReverseStates,
                      G,
                      Depth,
                      Heuristic,
                      Heap0,
                      Best0,
                      Sequence0,
                      Trace0,
                      Heap,
                      Best,
                      Sequence,
                      Trace) :-
    findall(instance(Id, Action, Add, Delete),
            applicable(Schema,
                       State,
                       instance(Id, Action, Add, Delete)),
            Instances),
    expand_instances(Instances,
                     Cost,
                     State,
                     ReverseSteps,
                     ReverseStates,
                     G,
                     Depth,
                     Heuristic,
                     Heap0,
                     Best0,
                     Sequence0,
                     Trace0,
                     Heap1,
                     Best1,
                     Sequence1,
                     Trace1),
    expand_costed_schemas(Rest,
                          State,
                          ReverseSteps,
                          ReverseStates,
                          G,
                          Depth,
                          Heuristic,
                          Heap1,
                          Best1,
                          Sequence1,
                          Trace1,
                          Heap,
                          Best,
                          Sequence,
                          Trace).

expand_instances([], _, _, _, _, _, _, _, Heap, Best, Sequence, Trace,
                 Heap, Best, Sequence, Trace).
expand_instances([instance(Id, Action, Add, Delete)|Rest],
                 Cost,
                 State,
                 ReverseSteps,
                 ReverseStates,
                 G,
                 Depth,
                 Heuristic,
                 Heap0,
                 Best0,
                 Sequence0,
                 Trace0,
                 Heap,
                 Best,
                 Sequence,
                 Trace) :-
    Instance = instance(Id, Action, Add, Delete),
    Step = step(Id, Action),
    apply_instance(Instance, State, NextState),
    CandidateG is G + Cost,
    (   NextState == State
    ->  Heap1 = Heap0,
        Best1 = Best0,
        Sequence1 = Sequence0,
        Trace1 = [no_progress(Step, State, CandidateG)|Trace0]
    ;   relax_state(NextState,
                    Step,
                    ReverseSteps,
                    ReverseStates,
                    CandidateG,
                    Depth,
                    Heuristic,
                    Heap0,
                    Best0,
                    Sequence0,
                    Trace0,
                    Heap1,
                    Best1,
                    Sequence1,
                    Trace1)
    ),
    expand_instances(Rest,
                     Cost,
                     State,
                     ReverseSteps,
                     ReverseStates,
                     G,
                     Depth,
                     Heuristic,
                     Heap1,
                     Best1,
                     Sequence1,
                     Trace1,
                     Heap,
                     Best,
                     Sequence,
                     Trace).

relax_state(State,
            Step,
            ReverseSteps,
            ReverseStates,
            CandidateG,
            Depth,
            Heuristic,
            Heap0,
            Best0,
            Sequence0,
            Trace0,
            Heap,
            Best,
            Sequence,
            Trace) :-
    (   get_assoc(State, Best0, OldG)
    ->  (   CandidateG < OldG
        ->  put_assoc(State, Best0, CandidateG, Best1),
            queue_state(State,
                        Step,
                        ReverseSteps,
                        ReverseStates,
                        CandidateG,
                        Depth,
                        Heuristic,
                        Heap0,
                        Sequence0,
                        Heap1,
                        Sequence1,
                        F),
            Trace1 = [improved(State, OldG, CandidateG, F, Step)|Trace0]
        ;   Best1 = Best0,
            Heap1 = Heap0,
            Sequence1 = Sequence0,
            Trace1 = [dominated(State, CandidateG, OldG, Step)|Trace0]
        )
    ;   put_assoc(State, Best0, CandidateG, Best1),
        queue_state(State,
                    Step,
                    ReverseSteps,
                    ReverseStates,
                    CandidateG,
                    Depth,
                    Heuristic,
                    Heap0,
                    Sequence0,
                    Heap1,
                    Sequence1,
                    F),
        Trace1 = [discovered(State, CandidateG, F, Step)|Trace0]
    ),
    Heap = Heap1,
    Best = Best1,
    Sequence = Sequence1,
    Trace = Trace1.

queue_state(State,
            Step,
            ReverseSteps,
            ReverseStates,
            G,
            Depth,
            Heuristic,
            Heap0,
            Sequence0,
            Heap,
            Sequence,
            F) :-
    heuristic_value(Heuristic, State, H),
    F is G + H,
    NextDepth is Depth + 1,
    add_to_heap(Heap0,
                priority(F, Sequence0),
                node(State,
                     [Step|ReverseSteps],
                     [State|ReverseStates],
                     G,
                     NextDepth),
                Heap),
    Sequence is Sequence0 + 1.

prepare_heuristic(zero, zero) :-
    !.
prepare_heuristic(table(Entries), table(Assoc)) :-
    !,
    must_be(list, Entries),
    empty_assoc(Empty),
    add_estimates(Entries, Empty, Assoc).
prepare_heuristic(Term, _) :-
    throw(error(type_error(planning_heuristic, Term),
                context(cost_search,
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
                    context(cost_search,
                            'Duplicate heuristic state')))
    ;   put_assoc(State, Assoc0, H, Assoc1)
    ),
    add_estimates(Rest, Assoc1, Assoc).
add_estimates([Term|_], _, _) :-
    throw(error(type_error(heuristic_estimate, Term),
                context(cost_search,
                        'Expected estimate(State,H)'))).

heuristic_value(zero, _, 0).
heuristic_value(table(Assoc), State, H) :-
    (   get_assoc(State, Assoc, H)
    ->  true
    ;   throw(error(existence_error(heuristic_estimate, State),
                    context(cost_search,
                            'No heuristic estimate for generated state')))
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
                context(cost_search,
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
                context(cost_search,
                        'Expected schema(Id,Action,Preconditions,Add,Delete)'))).

require_nonvar(_, Term) :-
    nonvar(Term),
    !.
require_nonvar(Label, _) :-
    throw(error(instantiation_error,
                context(cost_search, Label))).

require_nonnegative_integer(_, Value) :-
    integer(Value),
    Value >= 0,
    !.
require_nonnegative_integer(Label, Value) :-
    (   integer(Value)
    ->  throw(error(domain_error(non_negative_integer, Value),
                    context(cost_search, Label)))
    ;   throw(error(type_error(integer, Value),
                    context(cost_search, Label)))
    ).
