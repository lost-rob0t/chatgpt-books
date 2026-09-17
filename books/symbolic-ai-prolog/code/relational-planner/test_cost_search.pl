:- begin_tests(cost_search).

:- use_module(planner, [breadth_first_plan/5, canonical_state/2]).
:- use_module(cost_search).
:- use_module(weighted_recovery_domain).

test(bfs_prefers_fewer_actions_even_when_more_expensive) :-
    weighted_recovery_schemas(Schemas),
    weighted_recovery_initial_state(Start),
    weighted_recovery_goal(Goal),
    breadth_first_plan(
        Schemas,
        Start,
        Goal,
        found(plan([step(remote_restore, remote_restore(node7))], _)),
        _).

test(ucs_prefers_lower_total_cost_and_reports_stale_entry) :-
    weighted_recovery_costed_schemas(Costed),
    weighted_recovery_initial_state(Start),
    weighted_recovery_goal(Goal),
    uniform_cost_plan(
        Costed,
        Start,
        Goal,
        found(plan(
            11,
            [ step(shuttle, shuttle(tech1, depot, site_a)),
              step(onsite_restore, onsite_restore(tech1, node7))
            ],
            States)),
        Trace),
    States = [CanonicalStart, SiteState, Final],
    canonical_state(Start, CanonicalStart),
    assertion(memberchk(restored(node7), Final)),
    assertion(memberchk(ticket_open(inc7), Final)),
    assertion(memberchk(stale(SiteState, 2, 1), Trace)).

test(equal_cost_rediscovery_is_dominated) :-
    weighted_recovery_costed_schemas(Costed),
    weighted_recovery_initial_state(Start),
    weighted_recovery_goal(Goal),
    uniform_cost_plan(Costed, Start, Goal, found(plan(11, _, _)), Trace),
    assertion(member(dominated(_State,
                               1,
                               1,
                               step(bus, bus(tech1, depot, site_a))),
                     Trace)).

test(a_star_audited_table_matches_ucs_cost) :-
    weighted_recovery_costed_schemas(Costed),
    weighted_recovery_initial_state(Start),
    weighted_recovery_goal(Goal),
    weighted_recovery_heuristic(Heuristic),
    uniform_cost_plan(Costed,
                      Start,
                      Goal,
                      found(plan(UcsCost, _, _)),
                      _),
    a_star_plan(Costed,
                Start,
                Goal,
                Heuristic,
                found(plan(AStarCost,
                           [ step(shuttle, shuttle(tech1, depot, site_a)),
                             step(onsite_restore,
                                  onsite_restore(tech1, node7))
                           ],
                           _)),
                _),
    assertion(UcsCost == 11),
    assertion(AStarCost == UcsCost).

test(overestimating_heuristic_can_return_costlier_goal) :-
    weighted_recovery_costed_schemas(Costed),
    weighted_recovery_initial_state(Start),
    weighted_recovery_goal(Goal),
    weighted_recovery_heuristic(
        table([ estimate(StartState, _),
                estimate(SiteState, _),
                estimate(RemoteGoalState, _),
                estimate(SiteGoalState, _)
              ])),
    Overestimating =
        table([ estimate(StartState, 0),
                estimate(SiteState, 100),
                estimate(RemoteGoalState, 0),
                estimate(SiteGoalState, 0)
              ]),
    uniform_cost_plan(Costed,
                      Start,
                      Goal,
                      found(plan(UcsCost, _, _)),
                      _),
    a_star_plan(Costed,
                Start,
                Goal,
                Overestimating,
                found(plan(AStarCost,
                           [step(remote_restore, remote_restore(node7))],
                           _)),
                _),
    assertion(UcsCost == 11),
    assertion(AStarCost == 12),
    assertion(AStarCost > UcsCost).

test(zero_heuristic_degenerates_to_ucs_on_fixture) :-
    weighted_recovery_costed_schemas(Costed),
    weighted_recovery_initial_state(Start),
    weighted_recovery_goal(Goal),
    uniform_cost_plan(Costed, Start, Goal, UcsResult, _),
    a_star_plan(Costed, Start, Goal, zero, AStarResult, _),
    assertion(AStarResult == UcsResult).

test(zero_cost_cycle_terminates_under_strict_improvement) :-
    Costed =
        [ costed(schema(to_b, to_b, [at(a)], [at(b)], [at(a)]), 0),
          costed(schema(to_a, to_a, [at(b)], [at(a)], [at(b)]), 0)
        ],
    uniform_cost_plan(Costed,
                      [at(a)],
                      [at(c)],
                      exhausted([at(c)]),
                      Trace),
    assertion(member(dominated([at(a)], 0, 0, step(to_a, to_a)), Trace)).

test(start_goal_has_zero_cost_and_zero_steps) :-
    weighted_recovery_costed_schemas(Costed),
    weighted_recovery_initial_state(Start),
    uniform_cost_plan(Costed,
                      Start,
                      [ticket_open(inc7)],
                      found(plan(0, [], [CanonicalStart])),
                      [expanded(CanonicalStart, 0, 0, 0)]),
    canonical_state(Start, CanonicalStart).

test(impossible_goal_exhausts_finite_weighted_domain) :-
    weighted_recovery_costed_schemas(Costed),
    weighted_recovery_initial_state(Start),
    weighted_recovery_impossible_goal(Goal),
    uniform_cost_plan(Costed,
                      Start,
                      Goal,
                      exhausted([restored(node999)]),
                      Trace),
    assertion(Trace \== []).

test(negative_cost_is_rejected,
     [throws(error(domain_error(non_negative_integer, -1), _))]) :-
    Schema = schema(noop, noop, [], [], []),
    uniform_cost_plan([costed(Schema, -1)], [], [], _, _).

test(non_integer_cost_is_rejected,
     [throws(error(type_error(integer, 1.5), _))]) :-
    Schema = schema(noop, noop, [], [], []),
    uniform_cost_plan([costed(Schema, 1.5)], [], [], _, _).

test(missing_heuristic_entry_is_rejected,
     [throws(error(existence_error(heuristic_estimate, _), _))]) :-
    weighted_recovery_costed_schemas(Costed),
    weighted_recovery_initial_state(Start),
    weighted_recovery_goal(Goal),
    a_star_plan(Costed,
                Start,
                Goal,
                table([estimate(Start, 11)]),
                _,
                _).

test(negative_heuristic_value_is_rejected,
     [throws(error(domain_error(non_negative_integer, -1), _))]) :-
    weighted_recovery_costed_schemas(Costed),
    weighted_recovery_initial_state(Start),
    weighted_recovery_goal(Goal),
    a_star_plan(Costed,
                Start,
                Goal,
                table([estimate(Start, -1)]),
                _,
                _).

test(non_integer_heuristic_value_is_rejected,
     [throws(error(type_error(integer, 1.5), _))]) :-
    weighted_recovery_costed_schemas(Costed),
    weighted_recovery_initial_state(Start),
    weighted_recovery_goal(Goal),
    a_star_plan(Costed,
                Start,
                Goal,
                table([estimate(Start, 1.5)]),
                _,
                _).

test(duplicate_canonical_heuristic_state_is_rejected,
     [throws(error(permission_error(insert,
                                    heuristic_estimate,
                                    [alpha, beta]),
                   _))]) :-
    a_star_plan([], 
                [alpha, beta],
                [],
                table([ estimate([alpha, beta], 0),
                        estimate([beta, alpha], 0)
                      ]),
                _,
                _).

test(callable_heuristic_term_is_rejected_without_execution,
     [throws(error(type_error(planning_heuristic, throw(marker)), _))]) :-
    weighted_recovery_costed_schemas(Costed),
    weighted_recovery_initial_state(Start),
    weighted_recovery_goal(Goal),
    a_star_plan(Costed,
                Start,
                Goal,
                throw(marker),
                _,
                _).

:- end_tests(cost_search).
