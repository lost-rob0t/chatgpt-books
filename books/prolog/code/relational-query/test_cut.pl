:- begin_tests(community_cut).

% Deliberately wrong failure-lab helper.  It commits to the first generated
% path before checking whether that path is acceptable for the requested limit.
premature_cut_connection_within_hops(Start, Goal, Limit, Path, Hops) :-
    user:connection_with_hops(Start, Goal, Path, Hops),
    !,
    Hops =< Limit.

% The cut inside first_connection_path_cut/3 is local to that called predicate;
% it does not erase the caller's later clause.
outer_choice(primary(Path)) :-
    user:first_connection_path_cut(ada, ben, Path).
outer_choice(fallback).

test(direct_cut_matches_once_wrapper_on_fixture) :-
    user:first_connection_path(ada, ben, OncePath),
    user:first_connection_path_cut(ada, ben, CutPath),
    assertion(OncePath == [ada, lina, ben]),
    assertion(CutPath == OncePath).

test(underlying_accepted_relation_keeps_all_answers) :-
    findall(Path-Hops,
            user:connection_within_hops(ada, sam, 3, Path, Hops),
            Answers),
    assertion(Answers == [
        [ada, lina, ben, sam]-3,
        [ada, noor, ben, sam]-3
    ]).

test(first_acceptable_commits_after_qualification) :-
    findall(Path-Hops,
            user:first_connection_within_hops(ada, sam, 3, Path, Hops),
            Answers),
    assertion(Answers == [[ada, lina, ben, sam]-3]).

test(premature_cut_loses_later_valid_solution, [fail]) :-
    premature_cut_connection_within_hops(ada, sam, 3, _Path, _Hops).

test(correct_cut_recovers_later_valid_solution) :-
    user:first_connection_within_hops(ada, sam, 3, Path, Hops),
    assertion(Path == [ada, lina, ben, sam]),
    assertion(Hops == 3).

test(first_acceptable_is_not_shortest_path) :-
    user:first_connection_within_hops(ada, sam, 4, FirstPath, FirstHops),
    assertion(FirstPath == [ada, lina, noor, ben, sam]),
    assertion(FirstHops == 4),
    once(user:connection_within_hops(ada, sam, 4, _ShorterPath, 3)).

test(cut_is_local_to_called_predicate) :-
    findall(Result, outer_choice(Result), Results),
    assertion(Results == [primary([ada, lina, ben]), fallback]).

:- end_tests(community_cut).
