:- use_module(library(plunit)).
:- ensure_loaded(test_neurosymbolic_boundaries).

:- initialization(main, main).

main :-
    (   current_test_unit(neurosymbolic_boundaries, _)
    ->  true
    ;   format(user_error,
               'ERROR: neurosymbolic_boundaries test unit was not loaded~n',
               []),
        halt(2)
    ),
    (   run_tests([neurosymbolic_boundaries])
    ->  halt(0)
    ;   halt(1)
    ).
