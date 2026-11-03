:- begin_tests(prolog_rlm_lab).

:- use_module(prolog_rlm_lab).

% Chapter 29 study fixture, mirrored as lab-owned data.  The lab models the
% documented plan semantics; it does not run the upstream companion runtime.
study_plan(plan([
    tool(study_retrieve, input(topic), evidence),
    rlm(
        plan([
            tool(study_normalize, var(evidence), claim),
            tool(study_verify, var(claim), verdict),
            final(var(verdict))
        ]),
        verified),
    checkpoint(verified),
    final(var(verified))
])).

study_capabilities([
    tool(study_retrieve),
    rlm,
    tool(study_normalize),
    tool(study_verify),
    checkpoint
]).

study_budget(budget{max_steps:7, max_depth:2, max_tool_calls:3, max_model_calls:0}).

study_balance(balance{steps:7, depth:2, tool_calls:3, model_calls:0}).

% --- validate_plan/2: the closed plan language --------------------------

test(study_plan_validates_to_chapter_30_estimate) :-
    study_plan(Plan),
    validate_plan(Plan, ok(estimate(7, 2, 3, 0))).

test(minimal_plan_is_a_single_final) :-
    validate_plan(plan([final(input)]), ok(estimate(1, 1, 0, 0))).

test(unknown_operation_is_rejected_as_data) :-
    validate_plan(plan([call(shell(id))]),
                  error(unknown_operation(call(shell(id))))).

test(wrong_arity_operation_is_outside_the_closed_set) :-
    validate_plan(plan([tool(study_verify)]), Status),
    Status = error(unknown_operation(tool(study_verify))).

test(retry_estimates_child_work_by_attempts) :-
    validate_plan(plan([retry(3,
                             plan([tool(t, input, x),
                                   final(var(x))]),
                             y),
                        final(var(y))]),
                  ok(estimate(7, 2, 3, 0))).

test(duplicate_binding_is_rejected) :-
    validate_plan(plan([tool(t1, input, same),
                        tool(t2, var(same), same)]),
                  error(duplicate_binding(same))).

test(unbound_variable_is_rejected) :-
    validate_plan(plan([final(var(missing))]),
                  error(unbound_variable(missing))).

test(final_must_be_last) :-
    validate_plan(plan([final(input), tool(t, input, x)]),
                  error(bad_final(final_not_last))).

test(plan_without_final_is_rejected) :-
    validate_plan(plan([checkpoint(done)]),
                  error(bad_final(no_final))).

test(malformed_operation_shape_is_rejected) :-
    validate_plan(plan([tool(t, input, 42)]), Status),
    Status = error(malformed_operation(tool(t, input, 42))).

test(malformed_plan_container_is_rejected) :-
    validate_plan(not_a_plan([]), error(malformed_plan(not_a_plan([])))).

% --- static_budget_check/3: static cost before dynamic cost -------------

test(exact_fixture_budget_admits_the_study_plan) :-
    study_plan(Plan),
    study_budget(Budget),
    validate_plan(Plan, ok(Estimate)),
    static_budget_check(Estimate, Budget, ok(ready)).

test(one_step_over_static_budget_is_rejected) :-
    static_budget_check(estimate(8, 2, 3, 0),
                        budget{max_steps:7, max_depth:2,
                               max_tool_calls:3, max_model_calls:0},
                        error(budget_exceeded(max_steps, 8, 7))).

test(depth_two_is_rejected_by_a_depth_one_budget) :-
    % The Chapter 30 negative experiment: only the budget changes.
    static_budget_check(estimate(7, 2, 3, 0),
                        budget{max_steps:7, max_depth:1,
                               max_tool_calls:3, max_model_calls:0},
                        error(budget_exceeded(max_depth, 2, 1))).

test(malformed_budget_fails_closed) :-
    static_budget_check(estimate(1, 1, 0, 0), budget{max_steps:9},
                        error(malformed_budget(budget{max_steps:9}))).

% --- budget/3: one decreasing balance ------------------------------------

test(exact_spending_empties_the_balance) :-
    % Trace the budget path for a plan that spends exactly its remaining
    % budget: the last admissible charge drives the balance to zero.
    study_balance(B0),
    budget(charge(steps, 7), B0, ok(B1)),
    get_dict(steps, B1, 0),
    get_dict(depth, B1, 2),
    get_dict(tool_calls, B1, 3).

test(over_spending_fails_closed_without_partial_charge) :-
    study_balance(B0),
    budget(charge(steps, 7), B0, ok(B1)),
    budget(charge(steps, 1), B1, error(budget_exceeded(steps, 1, 0))),
    assertion(get_dict(steps, B1, 0)),
    assertion(get_dict(tool_calls, B1, 3)),
    assertion(get_dict(depth, B1, 2)).

test(nested_entry_spends_the_same_balance) :-
    % Chapter 30 invariant: a recursive child does not mint a fresh budget.
    % Return restores the depth slot only; spent cost stays spent.
    study_balance(B0),
    budget(enter_rlm, B0, ok(B1)),
    budget(charge(tool_calls, 2), B1, ok(B2)),
    budget(exit_rlm, B2, ok(B3)),
    get_dict(depth, B3, 2),
    get_dict(tool_calls, B3, 1),
    get_dict(steps, B3, 7),
    get_dict(model_calls, B3, 0).

test(depth_exhaustion_denies_entry) :-
    % The balance has two depth slots (root plan and one nested child plan),
    % mirroring max_depth:2 in the Chapter 29 fixture.  A third entry fails.
    study_balance(B0),
    budget(enter_rlm, B0, ok(B1)),
    budget(enter_rlm, B1, ok(B2)),
    get_dict(depth, B2, 0),
    budget(enter_rlm, B2, error(budget_exceeded(depth, 1, 0))).

test(nonpositive_charge_is_an_invalid_demand) :-
    study_balance(B0),
    budget(charge(steps, 0), B0, error(invalid_demand(charge(steps, 0)))).

test(unknown_balance_field_is_an_invalid_demand) :-
    study_balance(B0),
    budget(charge(pixels, 1), B0, error(invalid_demand(charge(pixels, 1)))).

% --- authorize/3: authority is not availability --------------------------

test(granted_tool_operation_is_authorized) :-
    study_capabilities(Caps),
    Op = tool(study_verify, var(claim), verdict),
    authorize(Op, Caps, ok(Op)).

test(ungranted_tool_is_denied_even_if_installed) :-
    % study_verify stays installed in the chapter's tool registry; the
    % capability list below omits it.  authorize/3 takes no registry
    % argument, so availability cannot rescue authority.
    Restricted = [tool(study_retrieve), rlm,
                  tool(study_normalize), checkpoint],
    authorize(tool(study_verify, var(claim), verdict), Restricted,
              error(capability_denied(tool(study_verify)))).

test(nested_rlm_requires_the_rlm_capability) :-
    Restricted = [tool(study_retrieve), tool(study_normalize),
                  tool(study_verify), checkpoint],
    authorize(rlm(plan([final(input)]), verified), Restricted,
              error(capability_denied(rlm))).

test(checkpoint_requires_its_capability) :-
    study_capabilities(Caps),
    authorize(checkpoint(verified), Caps, ok(checkpoint(verified))).

test(final_needs_no_capability) :-
    authorize(final(var(verified)), [], ok(final(var(verified)))).

test(authorize_rejects_unknown_operations_even_if_listed) :-
    % Membership in a capability list does not admit a term into the closed
    % operation vocabulary.
    authorize(shell(id), [shell], error(unknown_operation(shell(id)))).

:- end_tests(prolog_rlm_lab).
