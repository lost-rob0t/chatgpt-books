:- use_module(library(plunit)).
:- ensure_loaded('relational-query/test_community.pl').
:- ensure_loaded('relational-query/test_search.pl').

:- initialization(main, main).

main :-
    require_test_unit(community),
    require_test_unit(community_search),
    (   run_tests([community, community_search])
    ->  halt(0)
    ;   halt(1)
    ).

require_test_unit(Unit) :-
    (   current_test_unit(Unit, _)
    ->  true
    ;   format(user_error, 'ERROR: ~w test unit was not loaded~n', [Unit]),
        halt(2)
    ).
