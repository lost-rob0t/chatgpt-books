:- begin_tests(community_search).

:- use_module(library(time)).

test(topic_members_enumerate, all(Topic == [prolog, systems, debugging])) :-
    user:interested_in(ada, Topic).

test(absent_topic_fails, [fail]) :-
    user:interested_in(ada, databases).

test(hand_derived_reverse_relation) :-
    user:list_reverse([ada, lina, noor], [noor, lina, ada]).

test(path_relation_has_multiple_answers,
     set(Path == [[ada, lina, ben],
                  [ada, lina, noor, ben],
                  [ada, noor, ben]])) :-
    user:connection_path(ada, ben, Path).

test(paths_are_simple,
     [forall(user:connection_path(ada, ben, Path))]) :-
    sort(Path, Unique),
    length(Path, Length),
    length(Unique, Length).

test(cycle_safe_reverse_reachability,
     set(Path == [[noor, ada, lina]])) :-
    user:connection_path(noor, lina, Path).

test(unreachable_target_terminates_and_fails, [fail]) :-
    % SWI-specific test harness guard. This is not benchmark evidence.
    call_with_time_limit(1, user:connection_path(ada, nowhere, _)).

test(explicit_first_answer_commitment) :-
    user:first_connection_path(ada, ben, Path),
    assertion(Path == [ada, lina, ben]).

:- end_tests(community_search).
