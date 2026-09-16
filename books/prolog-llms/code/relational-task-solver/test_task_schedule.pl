:- begin_tests(task_schedule).

:- use_module(task_schedule).
:- use_module(library(clpfd)).

test(constraint_relation_posts_without_labeling) :-
    schedule_constraints(
        [ slot(collect_sources, Collect, 2),
          slot(normalize_terms, Normalize, 2),
          slot(validate_schema, Validate, 2),
          slot(verify_provenance, Verify, 3),
          slot(publish_report, Publish, 1)
        ],
        Makespan),
    assertion(var(Collect)),
    assertion(var(Normalize)),
    assertion(var(Validate)),
    assertion(var(Verify)),
    assertion(var(Publish)),
    assertion(var(Makespan)).

test(first_minimum_schedule_is_exact) :-
    first_minimum_schedule(Schedule, Makespan),
    assertion(Makespan == 10),
    assertion(Schedule ==
              [ slot(collect_sources, 0, 2),
                slot(normalize_terms, 2, 2),
                slot(validate_schema, 4, 2),
                slot(verify_provenance, 6, 3),
                slot(publish_report, 9, 1)
              ]).

test(shared_verifier_overlap_is_rejected, [fail]) :-
    schedule_constraints(
        [ slot(collect_sources, _Collect, 2),
          slot(normalize_terms, _Normalize, 2),
          slot(validate_schema, Validate, 2),
          slot(verify_provenance, Verify, 3),
          slot(publish_report, _Publish, 1)
        ],
        _Makespan),
    Validate #= 4,
    Verify #= 5.

test(reverse_resource_order_is_feasible_but_slower) :-
    schedule_constraints(
        [ slot(collect_sources, Collect, 2),
          slot(normalize_terms, Normalize, 2),
          slot(validate_schema, Validate, 2),
          slot(verify_provenance, Verify, 3),
          slot(publish_report, Publish, 1)
        ],
        Makespan),
    Collect #= 0,
    Normalize #= 2,
    Verify #= 5,
    Validate #= 8,
    Publish #= 10,
    labeling([], [Collect, Normalize, Validate, Verify, Publish]),
    assertion(Makespan == 11).

test(deadline_flag_is_zero_at_deadline) :-
    deadline_flag(10, 10, Late),
    assertion(Late == 0).

test(deadline_flag_is_one_after_deadline) :-
    deadline_flag(10, 9, Late),
    assertion(Late == 1).

:- end_tests(task_schedule).
