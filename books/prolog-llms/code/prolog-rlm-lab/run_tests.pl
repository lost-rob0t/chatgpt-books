:- use_module(library(plunit)).
:- ensure_loaded(test_prolog_rlm_lab).

:- initialization(main, main).

main :-
    (   current_test_unit(prolog_rlm_lab, _)
    ->  true
    ;   format(user_error, 'ERROR: prolog_rlm_lab test unit was not loaded~n', []),
        halt(2)
    ),
    (   run_tests([prolog_rlm_lab])
    ->  halt(0)
    ;   halt(1)
    ).
