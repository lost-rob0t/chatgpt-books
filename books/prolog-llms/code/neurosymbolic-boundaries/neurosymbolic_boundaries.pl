:- module(neurosymbolic_boundaries,
          [ validate_formalization/3,
            narrow_capabilities/3,
            validate_proof_provenance/3
          ]).

known_task(Task) :-
    memberchk(Task,
              [ collect_sources,
                normalize_terms,
                validate_schema,
                verify_provenance,
                publish_report
              ]).

known_resource(Resource) :-
    memberchk(Resource, [verifier, parser]).

validate_formalization(RequiredIds, Claims, Outcome) :-
    (   valid_id_list(RequiredIds)
    ->  validate_claim_list(RequiredIds, Claims, Outcome)
    ;   Outcome = error(invalid_required_ids)
    ).

validate_claim_list(RequiredIds, Claims, Outcome) :-
    (   is_list(Claims),
        ground(Claims)
    ->  validate_claims(RequiredIds, Claims, Validation)
    ;   Validation = error(invalid_claim_list)
    ),
    (   Validation = ok
    ->  validate_coverage(RequiredIds, Claims, Outcome)
    ;   Outcome = Validation
    ).

validate_claims(_, [], ok).
validate_claims(RequiredIds, [Claim|Rest], Outcome) :-
    validate_claim(RequiredIds, Claim, ClaimOutcome),
    (   ClaimOutcome = ok
    ->  validate_claims(RequiredIds, Rest, Outcome)
    ;   Outcome = ClaimOutcome
    ).

validate_claim(RequiredIds,
               claim(ClaimId, RequirementId, Requirement, source(SourceId)),
               Outcome) :-
    !,
    (   atom(ClaimId),
        atom(RequirementId),
        atom(SourceId)
    ->  (   memberchk(RequirementId, RequiredIds)
        ->  validate_requirement(Requirement, Outcome)
        ;   Outcome = error(unexpected_requirement(RequirementId))
        )
    ;   Outcome = error(invalid_claim_identity)
    ).
validate_claim(_, _, error(invalid_claim_shape)).

validate_requirement(duration(Task, Minutes), Outcome) :-
    !,
    (   known_task(Task)
    ->  (   integer(Minutes),
            Minutes >= 0,
            Minutes =< 1440
        ->  Outcome = ok
        ;   Outcome = error(invalid_duration(Task, Minutes))
        )
    ;   Outcome = error(unknown_task(Task))
    ).
validate_requirement(before(Earlier, Later), Outcome) :-
    !,
    (   known_task(Earlier)
    ->  (   known_task(Later)
        ->  (   Earlier \== Later
            ->  Outcome = ok
            ;   Outcome = error(invalid_self_precedence(Earlier))
            )
        ;   Outcome = error(unknown_task(Later))
        )
    ;   Outcome = error(unknown_task(Earlier))
    ).
validate_requirement(release(Task, Minute), Outcome) :-
    !,
    (   known_task(Task)
    ->  (   integer(Minute),
            Minute >= 0,
            Minute =< 1440
        ->  Outcome = ok
        ;   Outcome = error(invalid_release(Task, Minute))
        )
    ;   Outcome = error(unknown_task(Task))
    ).
validate_requirement(shared_resource(Resource, Left, Right), Outcome) :-
    !,
    (   known_resource(Resource)
    ->  validate_resource_tasks(Left, Right, Outcome)
    ;   Outcome = error(unknown_resource(Resource))
    ).
validate_requirement(Requirement, error(unknown_constructor(Name))) :-
    (   compound(Requirement)
    ->  functor(Requirement, Name, _)
    ;   Name = Requirement
    ).

validate_resource_tasks(Left, Right, Outcome) :-
    (   known_task(Left)
    ->  (   known_task(Right)
        ->  (   Left \== Right
            ->  Outcome = ok
            ;   Outcome = error(invalid_shared_resource_pair(Left))
            )
        ;   Outcome = error(unknown_task(Right))
        )
    ;   Outcome = error(unknown_task(Left))
    ).

validate_coverage(RequiredIds, Claims, Outcome) :-
    (   first_duplicate_requirement(Claims, Duplicate)
    ->  Outcome = error(duplicate_requirement(Duplicate))
    ;   first_uncovered_requirement(RequiredIds, Claims, Missing)
    ->  Outcome = error(uncovered_requirement(Missing))
    ;   Outcome = ok(accepted(Claims))
    ).

first_duplicate_requirement(Claims, Duplicate) :-
    member(claim(_, Duplicate, _, _), Claims),
    findall(1,
            member(claim(_, Duplicate, _, _), Claims),
            Matches),
    length(Matches, Count),
    Count > 1,
    !.

first_uncovered_requirement([Required|_], Claims, Required) :-
    \+ memberchk(claim(_, Required, _, _), Claims),
    !.
first_uncovered_requirement([_|Rest], Claims, Missing) :-
    first_uncovered_requirement(Rest, Claims, Missing).

narrow_capabilities(Parent, Requested, Outcome) :-
    (   valid_capability_list(Parent),
        valid_capability_list(Requested)
    ->  first_missing_capability(Requested, Parent, Missing, Check)
    ;   Check = error(invalid_capability_set)
    ),
    (   Check = ok
    ->  Outcome = ok(Requested)
    ;   Check = error(capability_widening(Missing))
    ->  Outcome = error(capability_widening(Missing))
    ;   Outcome = Check
    ).

first_missing_capability([], _, _, ok).
first_missing_capability([Capability|_], Parent, Capability,
                         error(capability_widening(Capability))) :-
    \+ memberchk(Capability, Parent),
    !.
first_missing_capability([_|Rest], Parent, Missing, Outcome) :-
    first_missing_capability(Rest, Parent, Missing, Outcome).

validate_proof_provenance(AcceptedClaimIds, Proof, Outcome) :-
    (   valid_id_list(AcceptedClaimIds)
    ->  validate_proof_shape(AcceptedClaimIds, Proof, Outcome)
    ;   Outcome = error(invalid_accepted_claim_ids)
    ).

validate_proof_shape(AcceptedClaimIds,
                     proof(QueryId, PremiseIds),
                     Outcome) :-
    !,
    (   atom(QueryId),
        valid_id_list(PremiseIds)
    ->  first_unaccepted_premise(PremiseIds, AcceptedClaimIds, Missing, Check)
    ;   Check = error(invalid_proof_shape)
    ),
    (   Check = ok
    ->  Outcome = ok(proof(QueryId, PremiseIds))
    ;   Check = error(unaccepted_premise(Missing))
    ->  Outcome = error(unaccepted_premise(Missing))
    ;   Outcome = Check
    ).
validate_proof_shape(_, _, error(invalid_proof_shape)).

first_unaccepted_premise([], _, _, ok).
first_unaccepted_premise([Premise|_], Accepted, Premise,
                         error(unaccepted_premise(Premise))) :-
    \+ memberchk(Premise, Accepted),
    !.
first_unaccepted_premise([_|Rest], Accepted, Missing, Outcome) :-
    first_unaccepted_premise(Rest, Accepted, Missing, Outcome).

valid_id_list(List) :-
    is_list(List),
    ground(List),
    maplist(atom, List),
    sort(List, Sorted),
    length(List, Length),
    length(Sorted, Length).

valid_capability_list(List) :-
    valid_id_list(List).
