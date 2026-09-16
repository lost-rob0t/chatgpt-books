:- begin_tests(symbolic_meta_interpreter).

:- use_module(meta_interpreter).
:- use_module(programs).

test(fact_yields_provenance_node) :-
    incident_program(Program),
    once(prove(Program,
               powered(gateway),
               fact(f_power_gateway, powered(gateway)))).

test(conjunction_preserves_child_order) :-
    incident_program(Program),
    once(prove(Program,
               (powered(gateway), link(gateway, router)),
               and(fact(f_power_gateway, powered(gateway)),
                   fact(f_link_gateway_router, link(gateway, router))))).

test(alternative_rules_backtrack_to_distinct_proofs) :-
    incident_program(Program),
    findall(Id,
            ( prove(Program, risk(alpha), Proof),
              Proof = step(Id, risk(alpha), _)
            ),
            Ids),
    assertion(Ids == [r_risk_temp, r_risk_fan]).

test(recursive_rule_variables_are_fresh_per_use) :-
    incident_program(Program),
    once(prove(Program, reachable(gateway, database), _)).

test(unsupported_goal_fails, [fail]) :-
    incident_program(Program),
    prove(Program, imaginary(gateway), _).

test(naive_interpreter_reaches_host_depth_guard) :-
    diagnostic_program(Program),
    call_with_depth_limit(prove(Program, unstable(sensor), _),
                          40,
                          Result),
    assertion(Result == depth_limit_exceeded).

test(guarded_interpreter_reports_direct_cycle) :-
    diagnostic_program(Program),
    once(prove_guarded(Program,
                       unstable(sensor),
                       10,
                       cycle(unstable(sensor)))).

test(guarded_cycle_does_not_hide_later_rule) :-
    Program = [rule(r_loop, stable(X), stable(X)),
               rule(r_base, stable(ok), true)],
    findall(Outcome,
            prove_guarded(Program, stable(ok), 4, Outcome),
            Outcomes),
    assertion(Outcomes == [cycle(stable(ok)),
                           proved(fact(r_base, stable(ok)))]).

test(guarded_interpreter_reports_rule_budget_exhaustion) :-
    diagnostic_program(Program),
    once(prove_guarded(Program,
                       grow(seed),
                       2,
                       exhausted(grow(s(s(seed)))))).

test(guarded_interpreter_can_prove_recursive_goal) :-
    incident_program(Program),
    once(prove_guarded(Program,
                       reachable(gateway, database),
                       8,
                       proved(_))).

test(provenance_is_preorder_rule_sequence) :-
    incident_program(Program),
    once(prove(Program, reachable(gateway, database), Proof)),
    proof_rule_ids(Proof, Ids),
    assertion(Ids == [r_reach_step,
                      f_link_gateway_router,
                      r_reach_step,
                      f_link_router_cache,
                      r_reach_direct,
                      f_link_cache_database]).

test(bundled_incident_rule_ids_are_unique) :-
    incident_program(Program),
    findall(Id, member(rule(Id, _, _), Program), Ids),
    sort(Ids, Unique),
    length(Ids, Count),
    length(Unique, Count).

test(negative_rule_budget_is_rejected,
     [error(type_error(nonneg, -1))]) :-
    incident_program(Program),
    prove_guarded(Program, powered(gateway), -1, _).

:- end_tests(symbolic_meta_interpreter).
