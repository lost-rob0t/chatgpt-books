:- module(bounded_search,
          [ depth_limited_plan/6,
            iterative_deepening_plan/6
          ]).

:- use_module(library(error), [must_be/2]).
:- use_module(planner,
              [ applicable/3,
                apply_instance/3,
                canonical_state/2,
                goal_satisfied/2
              ]).

%% depth_limited_plan(+Schemas, +Start, +Goals, +Limit, -Result, -Trace) is det.
%
% Run depth-first planning with a caller-visible maximum action depth.
% Result is one of:
%   found(plan(Steps, States))
%   cutoff(Goals, Limit)
%   exhausted(Goals)
%
% cutoff/2 means at least one live branch reached the requested boundary.
% exhausted/1 is returned only when every simple branch explored by this
% path-local cycle policy ended without a goal and without a depth cutoff.
depth_limited_plan(Schemas, Start0, Goals0, Limit, Result, Trace) :-
    validate_limit(Limit),
    validate_schemas(Schemas),
    canonical_state(Start0, Start),
    canonical_state(Goals0, Goals),
    depth_node(Schemas,
               Goals,
               Start,
               [],
               [Start],
               0,
               Limit,
               [Start],
               Result,
               Trace).

%% iterative_deepening_plan(+Schemas, +Start, +Goals, +MaxDepth,
%%                          -Result, -Trace) is det.
%
% Repeat depth-limited DFS at limits 0..MaxDepth.  A genuine exhausted/1
% iteration stops the process early: if no branch was cut off at that limit,
% raising the limit cannot reveal a deeper simple branch under the same
% transition and path-cycle semantics.  Reaching MaxDepth after only cutoffs
% remains cutoff/2 rather than being mislabeled as failure.
iterative_deepening_plan(Schemas, Start0, Goals0, MaxDepth, Result, Trace) :-
    validate_limit(MaxDepth),
    validate_schemas(Schemas),
    canonical_state(Start0, Start),
    canonical_state(Goals0, Goals),
    iterative_loop(Schemas,
                   Start,
                   Goals,
                   0,
                   MaxDepth,
                   Result,
                   Trace).

iterative_loop(Schemas,
               Start,
               Goals,
               Limit,
               MaxDepth,
               Result,
               [iteration(Limit, Kind, IterationTrace)|RestTrace]) :-
    depth_limited_plan(Schemas,
                       Start,
                       Goals,
                       Limit,
                       IterationResult,
                       IterationTrace),
    result_kind(IterationResult, Kind),
    (   IterationResult = found(_)
    ->  Result = IterationResult,
        RestTrace = []
    ;   IterationResult = exhausted(_)
    ->  Result = IterationResult,
        RestTrace = []
    ;   Limit < MaxDepth
    ->  NextLimit is Limit + 1,
        iterative_loop(Schemas,
                       Start,
                       Goals,
                       NextLimit,
                       MaxDepth,
                       Result,
                       RestTrace)
    ;   Result = cutoff(Goals, MaxDepth),
        RestTrace = []
    ).

result_kind(found(_), found).
result_kind(cutoff(_, _), cutoff).
result_kind(exhausted(_), exhausted).

depth_node(Schemas,
           Goals,
           State,
           ReverseSteps,
           ReverseStates,
           Depth,
           Limit,
           PathStates,
           Result,
           [expanded(State, Depth, Limit)|Trace]) :-
    (   goal_satisfied(Goals, State)
    ->  reverse(ReverseSteps, Steps),
        reverse(ReverseStates, States),
        Result = found(plan(Steps, States)),
        Trace = []
    ;   successor_children(Schemas, State, Children),
        (   Depth >= Limit
        ->  boundary_outcome(Children,
                             PathStates,
                             Goals,
                             Depth,
                             Limit,
                             Result,
                             Trace)
        ;   NextDepth is Depth + 1,
            search_children(Children,
                            Schemas,
                            Goals,
                            ReverseSteps,
                            ReverseStates,
                            NextDepth,
                            Limit,
                            PathStates,
                            Result,
                            Trace)
        )
    ).

boundary_outcome(Children,
                 PathStates,
                 Goals,
                 Depth,
                 Limit,
                 Result,
                 Trace) :-
    classify_boundary_children(Children,
                               PathStates,
                               Depth,
                               CycleTrace,
                               HasLiveChild),
    (   HasLiveChild == true
    ->  Result = cutoff(Goals, Limit),
        append(CycleTrace,
               [cutoff_at_depth(Depth, Limit)],
               Trace)
    ;   Result = exhausted(Goals),
        Trace = CycleTrace
    ).

classify_boundary_children([], _, _, [], false).
classify_boundary_children([child(Step, State)|Rest],
                           PathStates,
                           Depth,
                           Trace,
                           HasLiveChild) :-
    (   memberchk(State, PathStates)
    ->  Trace = [cycle_pruned(Step, State, Depth)|RestTrace],
        classify_boundary_children(Rest,
                                   PathStates,
                                   Depth,
                                   RestTrace,
                                   HasLiveChild)
    ;   HasLiveChild = true,
        Trace = []
    ).

search_children([], _, Goals, _, _, _, _, _, exhausted(Goals), []).
search_children([child(Step, NextState)|Rest],
                Schemas,
                Goals,
                ReverseSteps,
                ReverseStates,
                Depth,
                Limit,
                PathStates,
                Result,
                Trace) :-
    (   memberchk(NextState, PathStates)
    ->  Trace = [cycle_pruned(Step, NextState, Depth)|RestTrace],
        search_children(Rest,
                        Schemas,
                        Goals,
                        ReverseSteps,
                        ReverseStates,
                        Depth,
                        Limit,
                        PathStates,
                        Result,
                        RestTrace)
    ;   depth_node(Schemas,
                   Goals,
                   NextState,
                   [Step|ReverseSteps],
                   [NextState|ReverseStates],
                   Depth,
                   Limit,
                   [NextState|PathStates],
                   ChildResult,
                   ChildTrace),
        (   ChildResult = found(_)
        ->  Result = ChildResult,
            Trace = ChildTrace
        ;   search_children(Rest,
                            Schemas,
                            Goals,
                            ReverseSteps,
                            ReverseStates,
                            Depth,
                            Limit,
                            PathStates,
                            RestResult,
                            RestTrace),
            (   RestResult = found(_)
            ->  Result = RestResult
            ;   combine_nonfound(ChildResult,
                                 RestResult,
                                 Goals,
                                 Limit,
                                 Result)
            ),
            append(ChildTrace, RestTrace, Trace)
        )
    ).

combine_nonfound(cutoff(_, _), _, Goals, Limit, cutoff(Goals, Limit)) :-
    !.
combine_nonfound(_, cutoff(_, _), Goals, Limit, cutoff(Goals, Limit)) :-
    !.
combine_nonfound(exhausted(_), exhausted(_), Goals, _, exhausted(Goals)).

successor_children(Schemas, State, Children) :-
    findall(child(step(Id, Action), NextState),
            ( member(Schema, Schemas),
              applicable(Schema,
                         State,
                         instance(Id, Action, Add, Delete)),
              apply_instance(instance(Id, Action, Add, Delete),
                             State,
                             NextState),
              NextState \== State
            ),
            Children).

validate_schemas(Schemas) :-
    must_be(list, Schemas),
    maplist(validate_schema, Schemas).

validate_schema(schema(Id, Action, Preconditions, Add, Delete)) :-
    !,
    must_be(atom, Id),
    require_nonvar(planning_action_template, Action),
    must_be(list, Preconditions),
    must_be(list, Add),
    must_be(list, Delete).
validate_schema(Term) :-
    throw(error(type_error(planning_schema, Term),
                context(bounded_search,
                        'Expected schema(Id,Action,Preconditions,Add,Delete)'))).

validate_limit(Limit) :-
    (   integer(Limit)
    ->  (   Limit >= 0
        ->  true
        ;   throw(error(domain_error(non_negative_integer, Limit),
                        context(bounded_search, depth_limit)))
        )
    ;   throw(error(type_error(integer, Limit),
                    context(bounded_search, depth_limit)))
    ).

require_nonvar(_, Term) :-
    nonvar(Term),
    !.
require_nonvar(Label, _) :-
    throw(error(instantiation_error,
                context(bounded_search, Label))).
