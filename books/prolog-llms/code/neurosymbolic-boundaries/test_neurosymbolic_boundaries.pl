:- begin_tests(neurosymbolic_boundaries).

:- use_module(neurosymbolic_boundaries).

valid_claims([
    claim(c_duration,
          r_duration,
          duration(normalize_terms, 2),
          source(spec_span_1)),
    claim(c_order,
          r_order,
          before(normalize_terms, validate_schema),
          source(spec_span_2))
]).

test(accepts_closed_formalization) :-
    valid_claims(Claims),
    validate_formalization([r_duration, r_order], Claims, Outcome),
    assertion(Outcome == ok(accepted(Claims))).

test(rejects_unknown_constructor) :-
    Claims = [claim(c_unknown,
                    r_duration,
                    arbitrary_goal(call(halt)),
                    source(spec_span_1))],
    validate_formalization([r_duration], Claims, Outcome),
    assertion(Outcome == error(unknown_constructor(arbitrary_goal))).

test(rejects_uncovered_requirement) :-
    Claims = [claim(c_duration,
                    r_duration,
                    duration(normalize_terms, 2),
                    source(spec_span_1))],
    validate_formalization([r_duration, r_order], Claims, Outcome),
    assertion(Outcome == error(uncovered_requirement(r_order))).

test(rejects_unexpected_requirement) :-
    Claims = [claim(c_extra,
                    r_not_requested,
                    release(validate_schema, 3),
                    source(spec_span_9))],
    validate_formalization([r_duration], Claims, Outcome),
    assertion(Outcome == error(unexpected_requirement(r_not_requested))).

test(rejects_unknown_task) :-
    Claims = [claim(c_duration,
                    r_duration,
                    duration(invented_task, 2),
                    source(spec_span_1))],
    validate_formalization([r_duration], Claims, Outcome),
    assertion(Outcome == error(unknown_task(invented_task))).

test(rejects_negative_duration) :-
    Claims = [claim(c_duration,
                    r_duration,
                    duration(normalize_terms, -1),
                    source(spec_span_1))],
    validate_formalization([r_duration], Claims, Outcome),
    assertion(Outcome == error(invalid_duration(normalize_terms, -1))).

test(rejects_duplicate_requirement) :-
    Claims = [claim(c_duration_a,
                    r_duration,
                    duration(normalize_terms, 2),
                    source(spec_span_1)),
              claim(c_duration_b,
                    r_duration,
                    duration(normalize_terms, 3),
                    source(spec_span_2))],
    validate_formalization([r_duration], Claims, Outcome),
    assertion(Outcome == error(duplicate_requirement(r_duration))).

test(child_capabilities_may_narrow) :-
    narrow_capabilities([lookup, summarize], [lookup], Outcome),
    assertion(Outcome == ok([lookup])).

test(child_capabilities_may_not_widen) :-
    narrow_capabilities([lookup, summarize],
                        [lookup, write_file],
                        Outcome),
    assertion(Outcome == error(capability_widening(write_file))).

test(proof_provenance_accepts_only_accepted_claims) :-
    validate_proof_provenance([c_duration, c_order],
                              proof(q_ready, [c_duration, c_order]),
                              Outcome),
    assertion(Outcome == ok(proof(q_ready, [c_duration, c_order]))).

test(proof_provenance_rejects_unaccepted_claim) :-
    validate_proof_provenance([c_duration],
                              proof(q_ready, [c_duration, c_forged]),
                              Outcome),
    assertion(Outcome == error(unaccepted_premise(c_forged))).

test(rejects_duplicate_accepted_claim_ids) :-
    validate_proof_provenance([c_duration, c_duration],
                              proof(q_ready, [c_duration]),
                              Outcome),
    assertion(Outcome == error(invalid_accepted_claim_ids)).

:- end_tests(neurosymbolic_boundaries).
