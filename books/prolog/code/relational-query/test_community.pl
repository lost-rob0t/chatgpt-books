:- begin_tests(community).

:- [community].

test(known_person) :-
    person(ada).

test(unknown_person, [fail]) :-
    person(zoe).

test(mentor_direction) :-
    mentor_of(ada, lina).

test(mentor_direction_is_not_implicit_reverse, [fail]) :-
    mentor_of(lina, ada).

test(same_neighborhood, set(Other == [lina])) :-
    same_neighborhood(ada, Other).

test(no_self_neighborhood, [fail]) :-
    same_neighborhood(ada, ada).

test(project_peers, set(Other-Project == [lina-atlas, noor-atlas])) :-
    project_peer(ada, Other, Project).

test(shared_variable_unification, true(Person == ada)) :-
    mentor_of(Person, lina),
    works_on(Person, atlas).

test(shared_variable_failure, [fail]) :-
    mentor_of(Person, lina),
    works_on(Person, beacon).

test(anonymous_variables_do_not_share) :-
    works_on(_, atlas),
    mentor(_, _).

test(sound_unification_rejects_new_cycle, [fail]) :-
    unify_with_occurs_check(X, node(X)).

:- end_tests(community).
