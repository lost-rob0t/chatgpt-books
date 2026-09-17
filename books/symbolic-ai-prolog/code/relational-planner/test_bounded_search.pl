:- begin_tests(bounded_search).

:- use_module(bounded_search).
:- use_module(field_service_domain).
:- use_module(planner, [canonical_state/2]).

test(limit_below_solution_reports_cutoff_not_exhaustion) :-
    field_service_schemas(Schemas),
    field_service_initial_state(Start),
    field_service_goal(Goal),
    depth_limited_plan(Schemas,
                       Start,
                       Goal,
                       2,
                       cutoff([restored(node7)], 2),
                       Trace),
    assertion(member(cutoff_at_depth(2, 2), Trace)).

test(exact_limit_finds_concrete_three_step_plan) :-
    field_service_schemas(Schemas),
    field_service_initial_state(Start),
    field_service_goal(Goal),
    depth_limited_plan(
        Schemas,
        Start,
        Goal,
        3,
        found(plan(
            [ step(pick_part, pick_up(tech1, psu42, depot)),
              step(travel, travel(tech1, depot, site_a)),
              step(replace_psu,
                   replace_psu(tech1, node7, psu42, psu_old))
            ],
            States)),
        _),
    States = [_, _, _, Final],
    assertion(memberchk(restored(node7), Final)).

test(iterative_deepening_exposes_cutoff_iterations_then_finds) :-
    field_service_schemas(Schemas),
    field_service_initial_state(Start),
    field_service_goal(Goal),
    iterative_deepening_plan(
        Schemas,
        Start,
        Goal,
        5,
        found(plan(Steps, _)),
        Trace),
    assertion(Steps =
        [ step(pick_part, pick_up(tech1, psu42, depot)),
          step(travel, travel(tech1, depot, site_a)),
          step(replace_psu,
               replace_psu(tech1, node7, psu42, psu_old))
        ]),
    findall(Limit-Kind,
            member(iteration(Limit, Kind, _), Trace),
            Outcomes),
    assertion(Outcomes == [0-cutoff, 1-cutoff, 2-cutoff, 3-found]).

test(iterative_deepening_maximum_remains_cutoff) :-
    field_service_schemas(Schemas),
    field_service_initial_state(Start),
    field_service_goal(Goal),
    iterative_deepening_plan(Schemas,
                             Start,
                             Goal,
                             2,
                             cutoff([restored(node7)], 2),
                             Trace),
    assertion(Trace = [ iteration(0, cutoff, _),
                        iteration(1, cutoff, _),
                        iteration(2, cutoff, _)
                      ]).

test(start_goal_is_found_at_depth_zero) :-
    field_service_schemas(Schemas),
    field_service_initial_state(Start),
    iterative_deepening_plan(Schemas,
                             Start,
                             [ticket_open(inc7)],
                             0,
                             found(plan([], [CanonicalStart])),
                             [iteration(0, found,
                                        [expanded(CanonicalStart, 0, 0)])]),
    canonical_state(Start, CanonicalStart).

test(finite_cycle_without_goal_exhausts_instead_of_cutoff) :-
    Schemas =
        [ schema(to_b, to_b, [at(a)], [at(b)], [at(a)]),
          schema(to_a, to_a, [at(b)], [at(a)], [at(b)])
        ],
    depth_limited_plan(Schemas,
                       [at(a)],
                       [at(c)],
                       4,
                       exhausted([at(c)]),
                       Trace),
    assertion(member(cycle_pruned(step(to_a, to_a), [at(a)], 2), Trace)).

test(iterative_deepening_stops_early_on_true_exhaustion) :-
    Schemas = [schema(to_b, to_b, [at(a)], [at(b)], [at(a)])],
    iterative_deepening_plan(Schemas,
                             [at(a)],
                             [at(c)],
                             10,
                             exhausted([at(c)]),
                             Trace),
    findall(Limit-Kind,
            member(iteration(Limit, Kind, _), Trace),
            Outcomes),
    assertion(Outcomes == [0-cutoff, 1-exhausted]).

test(negative_depth_limit_is_rejected,
     [throws(error(domain_error(non_negative_integer, -1), _))]) :-
    depth_limited_plan([], [], [], -1, _, _).

test(non_integer_depth_limit_is_rejected,
     [throws(error(type_error(integer, 1.5), _))]) :-
    iterative_deepening_plan([], [], [], 1.5, _, _).

:- end_tests(bounded_search).
