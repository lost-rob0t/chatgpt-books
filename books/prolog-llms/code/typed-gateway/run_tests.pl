:- use_module(library(plunit)).
:- ensure_loaded(test_typed_gateway).

:- initialization(main, main).

main :-
    (   current_test_unit(typed_gateway, _)
    ->  true
    ;   format(user_error, 'ERROR: typed_gateway test unit was not loaded~n', []),
        halt(2)
    ),
    (   run_tests([typed_gateway])
    ->  halt(0)
    ;   halt(1)
    ).
