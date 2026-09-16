:- begin_tests(community_arithmetic).

test(path_hops_counts_edges) :-
    user:path_hops([ada, lina, noor, ben], Hops),
    assertion(Hops == 3).

test(path_hops_single_node_is_zero) :-
    user:path_hops([ada], Hops),
    assertion(Hops == 0).

test(path_hops_empty_path_fails, [fail]) :-
    user:path_hops([], _).

test(connection_hops_preserve_all_paths,
     set(Hops-Path == [2-[ada, lina, ben],
                       2-[ada, noor, ben],
                       3-[ada, lina, noor, ben]])) :-
    user:connection_with_hops(ada, ben, Path, Hops).

test(within_two_hops_filters_after_proof,
     set(Path == [[ada, lina, ben],
                  [ada, noor, ben]])) :-
    user:connection_within_hops(ada, ben, 2, Path, _Hops).

test(within_one_hop_has_no_ada_ben_path, [fail]) :-
    user:connection_within_hops(ada, ben, 1, _Path, _Hops).

test(low_level_arithmetic_does_not_solve_backwards,
     [throws(error(instantiation_error, _))]) :-
    _Three is _Unknown + 2.

test(arithmetic_equality_is_not_term_unification) :-
    assertion(1 =:= 1.0),
    assertion(1 \= 1.0).

:- end_tests(community_arithmetic).
