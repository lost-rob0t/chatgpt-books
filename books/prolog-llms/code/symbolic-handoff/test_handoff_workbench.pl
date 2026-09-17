:- begin_tests(symbolic_handoff).

:- use_module(handoff_workbench).

host(host_context{request_id:"req-handoff-001",
                  source_id:"fixture-source-001"}).

test(closed_artifact_vocabulary_is_exact) :-
    setof(Kind, artifact_kind(Kind), Kinds),
    assertion(Kinds == [capability_request,
                        constraint_spec,
                        logic_theory,
                        planning_problem,
                        program_proposal,
                        subproblem_request]).

test(capability_request_normalizes_with_host_provenance) :-
    host(Context),
    normalize_artifact(Context,
                       artifact(capability_request,
                                request(tasks_by_owner, [ada])),
                       Outcome),
    Outcome = ok(Artifact),
    assertion(Artifact.kind == capability_request),
    assertion(Artifact.payload == request(tasks_by_owner, [ada])),
    assertion(Artifact.provenance ==
              provenance{request_id:"req-handoff-001",
                         source_id:"fixture-source-001"}).

test(capability_dispatch_reuses_project1_authority) :-
    host(Context),
    dispatch_artifact(Context,
                      artifact(capability_request,
                               request(tasks_by_owner, [ada])),
                      Outcome),
    Outcome = ok(Executed),
    assertion(Executed.kind == capability_request),
    assertion(Executed.provenance ==
              provenance{request_id:"req-handoff-001",
                         source_id:"fixture-source-001"}),
    assertion(Executed.results ==
              [result(task(collect_sources), owner(ada), status(ready),
                      tags([research,prolog])),
               result(task(check_constraints), owner(ada), status(blocked),
                      tags([prolog,validation]))]).

test(unknown_capability_fails_before_dispatch) :-
    host(Context),
    dispatch_artifact(Context,
                      artifact(capability_request, request(halt, [])),
                      Outcome),
    assertion(Outcome == error(unknown_capability)).

test(wrong_capability_arity_is_explicit) :-
    host(Context),
    normalize_artifact(Context,
                       artifact(capability_request,
                                request(tasks_by_owner, [ada, ben])),
                       Outcome),
    assertion(Outcome == error(wrong_capability_arity)).

test(program_source_remains_opaque_and_unexecuted) :-
    host(Context),
    dispatch_artifact(Context,
                      artifact(program_proposal,
                               program(python, "print(6 * 7)")),
                      Outcome),
    Outcome = unsupported(program_proposal,
                          generated_program_execution_not_authorized,
                          Artifact),
    assertion(Artifact.payload ==
              opaque_program{language:python, source:"print(6 * 7)"}).

test(prolog_looking_source_never_becomes_a_goal) :-
    host(Context),
    dispatch_artifact(Context,
                      artifact(program_proposal,
                               program(prolog, "halt.")),
                      Outcome),
    Outcome = unsupported(program_proposal,
                          generated_program_execution_not_authorized,
                          Artifact),
    assertion(Artifact.payload ==
              opaque_program{language:prolog, source:"halt."}).

test(deadline_constraint_executes_existing_clpfd_fixture) :-
    host(Context),
    dispatch_artifact(Context,
                      artifact(constraint_spec, deadline(10)),
                      Outcome),
    Outcome = ok(Executed),
    assertion(Executed.kind == constraint_spec),
    assertion(Executed.result.makespan == 10),
    assertion(Executed.result.late == 0),
    assertion(Executed.result.schedule ==
              [slot(collect_sources, 0, 2),
               slot(normalize_terms, 2, 2),
               slot(validate_schema, 4, 2),
               slot(verify_provenance, 6, 3),
               slot(publish_report, 9, 1)]).

test(deadline_constraint_can_report_late) :-
    host(Context),
    dispatch_artifact(Context,
                      artifact(constraint_spec, deadline(9)),
                      Outcome),
    Outcome = ok(Executed),
    assertion(Executed.result.makespan == 10),
    assertion(Executed.result.late == 1).

test(negative_deadline_is_rejected) :-
    host(Context),
    normalize_artifact(Context,
                       artifact(constraint_spec, deadline(-1)),
                       Outcome),
    assertion(Outcome == error(invalid_constraint_spec)).

test(logic_theory_is_validated_but_not_fake_executed) :-
    host(Context),
    Theory = theory([prop(owner, [collect_sources, ada]),
                     prop(depends_on, [publish_report, collect_sources])],
                    prop(ready, [collect_sources])),
    dispatch_artifact(Context,
                      artifact(logic_theory, Theory),
                      Outcome),
    Outcome = unsupported(logic_theory,
                          theorem_prover_not_implemented,
                          Artifact),
    assertion(Artifact.payload == Theory).

test(unknown_logic_relation_is_rejected) :-
    host(Context),
    normalize_artifact(Context,
                       artifact(logic_theory,
                                theory([prop(call, [halt])],
                                       prop(ready, [collect_sources]))),
                       Outcome),
    assertion(Outcome == error(invalid_logic_theory)).

test(planning_problem_stays_at_sibling_book_boundary) :-
    host(Context),
    dispatch_artifact(Context,
                      artifact(planning_problem,
                               problem(service_recovery, incident_17)),
                      Outcome),
    Outcome = unsupported(planning_problem,
                          planner_owned_by_symbolic_ai_prolog,
                          Artifact),
    assertion(Artifact.payload ==
              problem(service_recovery, incident_17)).

test(subproblem_request_is_bounded_but_runtime_is_disabled) :-
    host(Context),
    dispatch_artifact(Context,
                      artifact(subproblem_request,
                               subproblem(chunk_2, 3,
                                          "inspect the second evidence block")),
                      Outcome),
    Outcome = unsupported(subproblem_request,
                          recursive_runtime_not_enabled,
                          Artifact),
    assertion(Artifact.payload ==
              subproblem(chunk_2, 3,
                         "inspect the second evidence block")).

test(subproblem_depth_above_bound_is_rejected) :-
    host(Context),
    normalize_artifact(Context,
                       artifact(subproblem_request,
                                subproblem(chunk_9, 9, "too deep")),
                       Outcome),
    assertion(Outcome == error(invalid_subproblem_request)).

test(host_provenance_envelope_rejects_extra_authority_field) :-
    Context = host_context{request_id:"req-handoff-001",
                           source_id:"fixture-source-001",
                           authority:yes},
    normalize_artifact(Context,
                       artifact(constraint_spec, deadline(10)),
                       Outcome),
    assertion(Outcome == error(invalid_host_context)).

test(unknown_artifact_kind_is_rejected) :-
    host(Context),
    normalize_artifact(Context,
                       artifact(shell_command, "rm -rf /"),
                       Outcome),
    assertion(Outcome == error(unknown_artifact_kind)).

:- end_tests(symbolic_handoff).
