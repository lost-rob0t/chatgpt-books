:- use_module(library(plunit)).
:- ensure_loaded(test_task_solver).
:- ensure_loaded(test_task_language).

:- initialization(main, main).

main :-
    require_test_unit(relational_task_solver),
    require_test_unit(task_language),
    (   run_tests([relational_task_solver, task_language])
    ->  halt(0)
    ;   halt(1)
    ).

require_test_unit(Unit) :-
    (   current_test_unit(Unit, _)
    ->  true
    ;   format(user_error, 'ERROR: ~w test unit was not loaded~n', [Unit]),
        halt(2)
    ).
