:- use_module(library(plunit)).
:- ensure_loaded('relational-query/community.pl').
:- ensure_loaded('relational-query/test_community.pl').
:- ensure_loaded('relational-query/test_search.pl').
:- ensure_loaded('relational-query/test_arithmetic.pl').

:- initialization(main, main).

main :-
    require_test_unit(community),
    require_test_unit(community_search),
    require_test_unit(community_arithmetic),
    (   run_tests([community, community_search, community_arithmetic])
    ->  halt(0)
    ;   halt(1)
    ).

require_test_unit(Unit) :-
    (   current_test_unit(Unit, _)
    ->  true
    ;   format(user_error, 'ERROR: ~w test unit was not loaded~n', [Unit]),
        halt(2)
    ).
