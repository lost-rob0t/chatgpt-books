:- module(handoff_workbench,
          [ artifact_kind/1,
            normalize_artifact/3,
            dispatch_artifact/3
          ]).

:- use_module('../relational-task-solver/task_capability',
              [ capability/2,
                execute_capability/2
              ]).
:- use_module('../relational-task-solver/task_schedule',
              [ first_minimum_schedule/2,
                deadline_flag/3
              ]).

/** <module> Typed symbolic handoff workbench

A deterministic teaching boundary for comparing several architecture families
used in LLM + symbolic systems.  The input artifact is data.  Normalization may
recognize a closed artifact shape, but only repository-authored dispatch clauses
can execute anything.  Generated source text is deliberately retained as opaque
data and never passed to call/1, consult/1, term_to_atom/2, or a shell.

This module does not implement the external systems discussed in the manuscript.
It gives readers one local executable contract for asking the important question:
what exactly crosses from a model-facing representation into a symbolic engine?
*/

%! artifact_kind(?Kind:atom) is nondet.
%
%  The complete closed vocabulary understood by this teaching workbench.
artifact_kind(capability_request).
artifact_kind(program_proposal).
artifact_kind(constraint_spec).
artifact_kind(logic_theory).
artifact_kind(planning_problem).
artifact_kind(subproblem_request).

%! normalize_artifact(+HostContext, +Artifact, -Outcome) is det.
%
%  Validate host-owned provenance plus one closed artifact representation.
%  Outcome is ok(normalized_artifact{...}) or error(Reason).
normalize_artifact(HostContext, Artifact, Outcome) :-
    (   valid_host_context(HostContext, Provenance)
    ->  normalize_candidate(Artifact, Provenance, Outcome)
    ;   Outcome = error(invalid_host_context)
    ).

%! dispatch_artifact(+HostContext, +Artifact, -Outcome) is det.
%
%  Normalize first, then cross one repository-authored execution boundary.
%  Unsupported architecture families remain explicit data; this function never
%  invents a theorem prover, planner, or recursive model runtime.
dispatch_artifact(HostContext, Artifact, Outcome) :-
    normalize_artifact(HostContext, Artifact, Normalized),
    dispatch_normalized(Normalized, Outcome).

valid_host_context(Context, provenance{request_id:RequestId,
                                       source_id:SourceId}) :-
    is_dict(Context, host_context),
    dict_pairs(Context, host_context, Pairs),
    length(Pairs, 2),
    get_dict(request_id, Context, RequestId),
    get_dict(source_id, Context, SourceId),
    nonempty_text(RequestId),
    nonempty_text(SourceId).

normalize_candidate(artifact(Kind, Payload), Provenance, Outcome) :-
    !,
    (   artifact_kind(Kind)
    ->  normalize_payload(Kind, Payload, PayloadOutcome),
        attach_provenance(Kind, Provenance, PayloadOutcome, Outcome)
    ;   Outcome = error(unknown_artifact_kind)
    ).
normalize_candidate(_, _, error(invalid_artifact_shape)).

attach_provenance(Kind, Provenance, ok(Payload),
                  ok(normalized_artifact{kind:Kind,
                                         payload:Payload,
                                         provenance:Provenance})) :-
    !.
attach_provenance(_, _, error(Reason), error(Reason)).

normalize_payload(capability_request, request(Name, Arguments), Outcome) :-
    !,
    validate_capability_request(Name, Arguments, Outcome).
normalize_payload(capability_request, _, error(invalid_capability_request)).

normalize_payload(program_proposal,
                  program(Language, Source), Outcome) :-
    !,
    (   program_language(Language),
        string(Source),
        string_length(Source, Length),
        Length > 0
    ->  Outcome = ok(opaque_program{language:Language, source:Source})
    ;   Outcome = error(invalid_program_proposal)
    ).
normalize_payload(program_proposal, _, error(invalid_program_proposal)).

normalize_payload(constraint_spec, deadline(Maximum), Outcome) :-
    !,
    (   integer(Maximum),
        Maximum >= 0
    ->  Outcome = ok(deadline(Maximum))
    ;   Outcome = error(invalid_constraint_spec)
    ).
normalize_payload(constraint_spec, _, error(invalid_constraint_spec)).

normalize_payload(logic_theory, theory(Premises, Query), Outcome) :-
    !,
    (   proper_proposition_list(Premises),
        proposition(Query)
    ->  Outcome = ok(theory(Premises, Query))
    ;   Outcome = error(invalid_logic_theory)
    ).
normalize_payload(logic_theory, _, error(invalid_logic_theory)).

normalize_payload(planning_problem, problem(DomainId, ProblemId), Outcome) :-
    !,
    (   atom(DomainId),
        atom(ProblemId)
    ->  Outcome = ok(problem(DomainId, ProblemId))
    ;   Outcome = error(invalid_planning_problem)
    ).
normalize_payload(planning_problem, _, error(invalid_planning_problem)).

normalize_payload(subproblem_request,
                  subproblem(SubproblemId, Depth, Goal), Outcome) :-
    !,
    (   atom(SubproblemId),
        integer(Depth),
        between(0, 8, Depth),
        nonempty_text(Goal)
    ->  Outcome = ok(subproblem(SubproblemId, Depth, Goal))
    ;   Outcome = error(invalid_subproblem_request)
    ).
normalize_payload(subproblem_request, _, error(invalid_subproblem_request)).

validate_capability_request(Name, Arguments, Outcome) :-
    (   atom(Name),
        proper_atom_list(Arguments)
    ->  (   capability(Name, Arity)
        ->  length(Arguments, ActualArity),
            (   ActualArity =:= Arity
            ->  Outcome = ok(request(Name, Arguments))
            ;   Outcome = error(wrong_capability_arity)
            )
        ;   Outcome = error(unknown_capability)
        )
    ;   Outcome = error(invalid_capability_request)
    ).

dispatch_normalized(error(Reason), error(Reason)) :-
    !.
dispatch_normalized(ok(Artifact), Outcome) :-
    get_dict(kind, Artifact, Kind),
    dispatch_kind(Kind, Artifact, Outcome).

dispatch_kind(capability_request, Artifact, Outcome) :-
    !,
    get_dict(payload, Artifact, Request),
    get_dict(provenance, Artifact, Provenance),
    (   execute_capability(Request, Results)
    ->  Outcome = ok(executed{kind:capability_request,
                              results:Results,
                              provenance:Provenance})
    ;   Outcome = error(capability_execution_failed)
    ).
dispatch_kind(constraint_spec, Artifact, Outcome) :-
    !,
    get_dict(payload, Artifact, deadline(Deadline)),
    get_dict(provenance, Artifact, Provenance),
    first_minimum_schedule(Schedule, Makespan),
    deadline_flag(Makespan, Deadline, Late),
    Outcome = ok(executed{kind:constraint_spec,
                          result:schedule_result{schedule:Schedule,
                                                 makespan:Makespan,
                                                 late:Late},
                          provenance:Provenance}).
dispatch_kind(program_proposal, Artifact,
              unsupported(program_proposal,
                          generated_program_execution_not_authorized,
                          Artifact)) :-
    !.
dispatch_kind(logic_theory, Artifact,
              unsupported(logic_theory,
                          theorem_prover_not_implemented,
                          Artifact)) :-
    !.
dispatch_kind(planning_problem, Artifact,
              unsupported(planning_problem,
                          planner_owned_by_symbolic_ai_prolog,
                          Artifact)) :-
    !.
dispatch_kind(subproblem_request, Artifact,
              unsupported(subproblem_request,
                          recursive_runtime_not_enabled,
                          Artifact)).

program_language(python).
program_language(javascript).
program_language(prolog).

proper_atom_list([]).
proper_atom_list([Head|Tail]) :-
    atom(Head),
    proper_atom_list(Tail).

proper_proposition_list([]).
proper_proposition_list([Head|Tail]) :-
    proposition(Head),
    proper_proposition_list(Tail).

proposition(prop(Relation, Arguments)) :-
    allowed_relation(Relation, Arity),
    proper_atom_list(Arguments),
    length(Arguments, Arity).

allowed_relation(owner, 2).
allowed_relation(depends_on, 2).
allowed_relation(ready, 1).
allowed_relation(has_tag, 2).

nonempty_text(Value) :-
    (   atom(Value)
    ->  atom_length(Value, Length)
    ;   string(Value)
    ->  string_length(Value, Length)
    ),
    Length > 0.
