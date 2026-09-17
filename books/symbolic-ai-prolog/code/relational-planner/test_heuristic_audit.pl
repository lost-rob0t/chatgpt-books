:- begin_tests(heuristic_audit).

:- use_module(cost_search, [a_star_plan/6]).
:- use_module(heuristic_audit).
:- use_module(planner, [canonical_state/2]).
:- use_module(weighted_recovery_domain).

test(audited_table_passes_complete_finite_closure) :-
    weighted_recovery_costed_schemas(Costed),
    weighted_recovery_initial_state(Start),
    weighted_recovery_goal(Goal),
    weighted_recovery_heuristic(Heuristic),
    audit_heuristic(
        Costed,
        Start,
        Goal,
        Heuristic,
        10,
        audited(summary(4, 9),
                verdict(admissible_on_audited_states,
                        consistent_on_audited_edges),
                problems([]),
                unreachable_goal_states([]))).

test(zero_heuristic_passes_finite_audit) :-
    weighted_recovery_costed_schemas(Costed),
    weighted_recovery_initial_state(Start),
    weighted_recovery_goal(Goal),
    audit_heuristic(
        Costed,
        Start,
        Goal,
        zero,
        10,
        audited(summary(4, 9),
                verdict(admissible_on_audited_states,
                        consistent_on_audited_edges),
                problems([]),
                unreachable_goal_states([]))).

test(admissible_but_inconsistent_table_is_distinguished) :-
    weighted_recovery_costed_schemas(Costed),
    weighted_recovery_initial_state(Start),
    weighted_recovery_goal(Goal),
    weighted_recovery_heuristic(
        table([ estimate(RawStartState, _),
                estimate(RawSiteState, _),
                estimate(RemoteGoalState, _),
                estimate(SiteGoalState, _)
              ])),
    canonical_state(RawStartState, StartState),
    canonical_state(RawSiteState, SiteState),
    Heuristic =
        table([ estimate(RawStartState, 11),
                estimate(RawSiteState, 0),
                estimate(RemoteGoalState, 0),
                estimate(SiteGoalState, 0)
              ]),
    audit_heuristic(
        Costed,
        Start,
        Goal,
        Heuristic,
        10,
        audited(summary(4, 9),
                verdict(admissible_on_audited_states, inconsistent),
                problems(Problems),
                unreachable_goal_states([]))),
    assertion(\+ member(inadmissible(_, _, _), Problems)),
    assertion(member(inconsistent(StartState,
                                  step(shuttle,
                                       shuttle(tech1, depot, site_a)),
                                  11,
                                  1,
                                  SiteState,
                                  0),
                     Problems)),
    a_star_plan(Costed,
                Start,
                Goal,
                Heuristic,
                found(plan(11, _, _)),
                _).

test(overestimating_table_reports_exact_remaining_cost_violation) :-
    weighted_recovery_costed_schemas(Costed),
    weighted_recovery_initial_state(Start),
    weighted_recovery_goal(Goal),
    weighted_recovery_heuristic(
        table([ estimate(RawStartState, _),
                estimate(RawSiteState, _),
                estimate(RemoteGoalState, _),
                estimate(RawSiteGoalState, _)
              ])),
    canonical_state(RawSiteState, SiteState),
    canonical_state(RawSiteGoalState, SiteGoalState),
    Heuristic =
        table([ estimate(RawStartState, 0),
                estimate(RawSiteState, 100),
                estimate(RemoteGoalState, 0),
                estimate(RawSiteGoalState, 0)
              ]),
    audit_heuristic(
        Costed,
        Start,
        Goal,
        Heuristic,
        10,
        audited(summary(4, 9),
                verdict(inadmissible, inconsistent),
                problems(Problems),
                unreachable_goal_states([]))),
    assertion(member(inadmissible(SiteState, 100, 10), Problems)),
    assertion(member(inconsistent(SiteState,
                                  step(onsite_restore,
                                       onsite_restore(tech1, node7)),
                                  100,
                                  10,
                                  SiteGoalState,
                                  0),
                     Problems)).

test(state_cap_returns_cutoff_without_quality_verdict) :-
    weighted_recovery_costed_schemas(Costed),
    weighted_recovery_initial_state(Start),
    weighted_recovery_goal(Goal),
    weighted_recovery_heuristic(Heuristic),
    audit_heuristic(Costed,
                    Start,
                    Goal,
                    Heuristic,
                    2,
                    cutoff(state_limit(2),
                           summary(2, 4),
                           candidate(_))).

test(callable_heuristic_term_is_rejected_without_execution,
     [throws(error(type_error(planning_heuristic, throw(marker)), _))]) :-
    weighted_recovery_costed_schemas(Costed),
    weighted_recovery_initial_state(Start),
    weighted_recovery_goal(Goal),
    audit_heuristic(Costed,
                    Start,
                    Goal,
                    throw(marker),
                    10,
                    _).

test(admissible_inconsistent_heuristic_reopens_expanded_state) :-
    reopening_costed_schemas(Costed),
    reopening_start(Start),
    reopening_goal(Goal),
    reopening_heuristic(Heuristic),
    canonical_state([at(b)], BState),
    canonical_state([at(c)], CState),
    audit_heuristic(
        Costed,
        Start,
        Goal,
        Heuristic,
        10,
        audited(summary(5, 5),
                verdict(admissible_on_audited_states, inconsistent),
                problems(Problems),
                unreachable_goal_states([]))),
    assertion(\+ member(inadmissible(_, _, _), Problems)),
    assertion(member(inconsistent(BState,
                                  step(b_to_c, b_to_c),
                                  6,
                                  1,
                                  CState,
                                  0),
                     Problems)),
    a_star_plan(
        Costed,
        Start,
        Goal,
        Heuristic,
        found(plan(7,
                   [ step(to_b, to_b),
                     step(b_to_c, b_to_c),
                     step(c_to_goal, c_to_goal)
                   ],
                   _)),
        Trace),
    findall(G,
            member(expanded(CState, G, _, _), Trace),
            CExpansionCosts),
    assertion(CExpansionCosts == [4, 2]),
    assertion(member(improved(CState,
                              4,
                              2,
                              2,
                              step(b_to_c, b_to_c)),
                     Trace)).

reopening_costed_schemas(
    [ costed(schema(to_a,
                    to_a,
                    [at(start)],
                    [at(a)],
                    [at(start)]),
             2),
      costed(schema(to_b,
                    to_b,
                    [at(start)],
                    [at(b)],
                    [at(start)]),
             1),
      costed(schema(a_to_c,
                    a_to_c,
                    [at(a)],
                    [at(c)],
                    [at(a)]),
             2),
      costed(schema(b_to_c,
                    b_to_c,
                    [at(b)],
                    [at(c)],
                    [at(b)]),
             1),
      costed(schema(c_to_goal,
                    c_to_goal,
                    [at(c)],
                    [at(goal)],
                    [at(c)]),
             5)
    ]).

reopening_start([at(start)]).
reopening_goal([at(goal)]).

reopening_heuristic(
    table([ estimate([at(start)], 0),
            estimate([at(a)], 0),
            estimate([at(b)], 6),
            estimate([at(c)], 0),
            estimate([at(goal)], 0)
          ])).

:- end_tests(heuristic_audit).
