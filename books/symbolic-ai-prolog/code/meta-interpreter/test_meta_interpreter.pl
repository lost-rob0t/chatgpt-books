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

test(either_enumerates_left_then_right_proofs) :-
    Program = [rule(f_left, left(ok), true),
               rule(f_right, right(ok), true)],
    findall(Proof,
            prove(Program, either(left(ok), right(ok)), Proof),
            Proofs),
    assertion(Proofs == [choice(left, fact(f_left, left(ok))),
                         choice(right, fact(f_right, right(ok)))]).

test(guarded_either_cycle_does_not_hide_other_branch) :-
    incident_program(Incident),
    diagnostic_program(Diagnostic),
    append(Diagnostic, Incident, Program),
    findall(Outcome,
            prove_guarded(Program,
                          either(unstable(sensor), powered(gateway)),
                          4,
                          Outcome),
            Outcomes),
    assertion(Outcomes == [cycle(unstable(sensor)),
                           proved(choice(right,
                                         fact(f_power_gateway,
                                              powered(gateway))))]).

test(guarded_either_resets_budget_for_right_branch) :-
    Program = [rule(l_start, left_start, left_mid),
               rule(l_mid, left_mid, left_deeper),
               rule(l_finish, left_deeper, true),
               rule(r_start, right_start, right_done),
               rule(r_finish, right_done, true)],
    findall(Outcome,
            prove_guarded(Program,
                          either(left_start, right_start),
                          2,
                          Outcome),
            Outcomes),
    assertion(Outcomes == [exhausted(left_deeper),
                           proved(choice(right,
                                         step(r_start,
                                              right_start,
                                              fact(r_finish,
                                                   right_done))))]).

test(choice_proof_does_not_invent_provenance_id) :-
    incident_program(Program),
    once(prove(Program,
               either(powered(gateway), imaginary(gateway)),
               Proof)),
    proof_rule_ids(Proof, Ids),
    assertion(Ids == [f_power_gateway]).

test(search_report_records_failed_then_successful_rule) :-
    incident_program(Program),
    search_report(Program,
                  reachable(gateway, database),
                  8,
                  search(reachable(gateway, database), Attempts)),
    Attempts = [attempt(r_reach_direct, failed),
                attempt(r_reach_step, outcomes(Outcomes))],
    assertion(Outcomes = [proved(step(r_reach_step,
                                      reachable(gateway, database),
                                      _))]).

test(search_report_keeps_both_successful_rule_attempts) :-
    incident_program(Program),
    search_report(Program,
                  risk(alpha),
                  4,
                  search(risk(alpha), Attempts)),
    Attempts = [attempt(r_risk_temp,
                        outcomes([proved(step(r_risk_temp,
                                              risk(alpha),
                                              fact(f_symptom_temp,
                                                   symptom(alpha,
                                                           high_temp))))])),
                attempt(r_risk_fan,
                        outcomes([proved(step(r_risk_fan,
                                              risk(alpha),
                                              fact(f_symptom_fan,
                                                   symptom(alpha,
                                                           fan_stopped))))]))].

test(search_report_preserves_cycle_outcome) :-
    diagnostic_program(Program),
    search_report(Program,
                  unstable(sensor),
                  4,
                  search(unstable(sensor),
                         [attempt(r_loop,
                                  outcomes([cycle(unstable(sensor))]))])).

test(search_report_preserves_exhaustion_outcome) :-
    diagnostic_program(Program),
    search_report(Program,
                  grow(seed),
                  2,
                  search(grow(seed),
                         [attempt(r_grow,
                                  outcomes([exhausted(grow(s(s(seed))))]))])).

test(search_report_unsupported_goal_has_no_matching_attempts) :-
    incident_program(Program),
    search_report(Program,
                  imaginary(gateway),
                  4,
                  search(imaginary(gateway), [])).

test(search_report_zero_budget_blocks_before_rule_selection) :-
    incident_program(Program),
    search_report(Program,
                  powered(gateway),
                  0,
                  blocked(exhausted(powered(gateway)))).

test(search_report_rejects_nonground_goal,
     [error(instantiation_error)]) :-
    incident_program(Program),
    search_report(Program, risk(_), 4, _).

test(search_report_rejects_control_form,
     [error(domain_error(object_rule_goal, either(powered(gateway),
                                                   powered(router))))]) :-
    incident_program(Program),
    search_report(Program,
                  either(powered(gateway), powered(router)),
                  4,
                  _).

:- end_tests(symbolic_meta_interpreter).
