:- begin_tests(symbolic_meta_interpreter).

:- use_module(meta_interpreter).

sample_program([
    rule(f_power_gateway, powered(gateway), true),
    rule(f_link_gateway_router, link(gateway, router), true),
    rule(f_link_router_cache, link(router, cache), true),
    rule(f_link_cache_database, link(cache, database), true),
    rule(f_symptom_temp, symptom(alpha, high_temp), true),
    rule(f_symptom_fan, symptom(alpha, fan_stopped), true),
    rule(r_risk_temp, risk(Host), symptom(Host, high_temp)),
    rule(r_risk_fan, risk(Host), symptom(Host, fan_stopped)),
    rule(r_reach_direct, reachable(From, To), link(From, To)),
    rule(r_reach_step,
         reachable(From, To),
         (link(From, Via), reachable(Via, To))),
    rule(r_loop, unstable(Node), unstable(Node)),
    rule(r_grow, grow(Term), grow(s(Term)))
]).

test(fact_yields_provenance_node) :-
    sample_program(Program),
    prove(Program,
          powered(gateway),
          fact(f_power_gateway, powered(gateway))).

test(conjunction_preserves_child_order) :-
    sample_program(Program),
    prove(Program,
          (powered(gateway), link(gateway, router)),
          and(fact(f_power_gateway, powered(gateway)),
              fact(f_link_gateway_router, link(gateway, router)))).

test(alternative_rules_backtrack_to_distinct_proofs) :-
    sample_program(Program),
    findall(Id,
            ( prove(Program, risk(alpha), Proof),
              Proof = step(Id, risk(alpha), _)
            ),
            Ids),
    assertion(Ids == [r_risk_temp, r_risk_fan]).

test(recursive_rule_variables_are_fresh_per_use) :-
    sample_program(Program),
    prove(Program, reachable(gateway, database), _).

test(unsupported_goal_fails, [fail]) :-
    sample_program(Program),
    prove(Program, imaginary(gateway), _).

test(guarded_interpreter_reports_direct_cycle) :-
    sample_program(Program),
    prove_guarded(Program,
                  unstable(sensor),
                  10,
                  cycle(unstable(sensor))).

test(guarded_interpreter_reports_rule_budget_exhaustion) :-
    sample_program(Program),
    prove_guarded(Program,
                  grow(seed),
                  2,
                  exhausted(grow(s(s(seed))))).

test(guarded_interpreter_can_prove_recursive_goal) :-
    sample_program(Program),
    prove_guarded(Program,
                  reachable(gateway, database),
                  8,
                  proved(_)).

test(provenance_is_preorder_rule_sequence) :-
    sample_program(Program),
    once(prove(Program, reachable(gateway, database), Proof)),
    proof_rule_ids(Proof, Ids),
    assertion(Ids == [r_reach_step,
                      f_link_gateway_router,
                      r_reach_step,
                      f_link_router_cache,
                      r_reach_direct,
                      f_link_cache_database]).

test(bundled_rule_ids_are_unique) :-
    sample_program(Program),
    findall(Id, member(rule(Id, _, _), Program), Ids),
    sort(Ids, Unique),
    length(Ids, Count),
    length(Unique, Count).

:- end_tests(symbolic_meta_interpreter).
