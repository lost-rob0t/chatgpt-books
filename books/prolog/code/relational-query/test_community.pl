:- begin_tests(community).

test(known_person) :-
    user:person(ada).

test(unknown_person, [fail]) :-
    user:person(zoe).

test(mentor_direction) :-
    user:mentor_of(ada, lina).

test(mentor_direction_is_not_implicit_reverse, [fail]) :-
    user:mentor_of(lina, ada).

test(same_neighborhood, set(Other == [lina])) :-
    user:same_neighborhood(ada, Other).

test(no_self_neighborhood, [fail]) :-
    user:same_neighborhood(ada, ada).

test(project_peers, set(Other-Project == [lina-atlas, noor-atlas])) :-
    user:project_peer(ada, Other, Project).

test(shared_variable_unification, set(Person == [ada])) :-
    user:mentor_of(Person, lina),
    user:works_on(Person, atlas).

test(shared_variable_failure, [fail]) :-
    user:mentor_of(Person, lina),
    user:works_on(Person, beacon).

test(anonymous_variables_do_not_share) :-
    _ = ada,
    _ = lina.

test(sound_unification_rejects_new_cycle, [fail]) :-
    unify_with_occurs_check(X, node(X)).

:- end_tests(community).
