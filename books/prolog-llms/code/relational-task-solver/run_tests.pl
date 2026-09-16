:- use_module(library(plunit)).
:- ensure_loaded(test_task_solver).

:- initialization(main, main).

main :-
    (   current_test_unit(relational_task_solver, _)
    ->  true
    ;   format(user_error, 'ERROR: relational_task_solver test unit was not loaded~n', []),
        halt(2)
    ),
    (   run_tests([relational_task_solver])
    ->  halt(0)
    ;   halt(1)
    ).
