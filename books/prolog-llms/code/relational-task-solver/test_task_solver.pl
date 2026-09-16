:- begin_tests(relational_task_solver).

:- use_module(task_solver).

test(fact_query_binds_owner) :-
    task(collect_sources, Owner, ready, Tags),
    assertion(Owner == ada),
    assertion(Tags == [research, prolog]).

test(reversing_dependency_roles_does_not_infer_a_fact, [fail]) :-
    depends_on(collect_sources, normalize_terms).

test(shared_variable_joins_relations) :-
    findall(Task,
            ( task(Task, ada, _, _),
              has_tag(Task, prolog)
            ),
            Tasks),
    assertion(Tasks == [collect_sources, check_constraints]).

test(list_relation_finds_tag) :-
    has_tag(write_explanation, explanation).

test(active_tasks_are_relational) :-
    setof(Task, owned_active_task(lina, Task),
          [publish_report, write_explanation]).

test(direct_dependency_path) :-
    dependency_path(normalize_terms, collect_sources, Path),
    assertion(Path == [normalize_terms, collect_sources]).

test(transitive_dependency_path) :-
    dependency_path(publish_report, collect_sources, Path),
    assertion(Path == [publish_report,
                       write_explanation,
                       check_constraints,
                       normalize_terms,
                       collect_sources]).

test(missing_dependency_path_fails, [fail]) :-
    dependency_path(collect_sources, publish_report, _).

test(task_explanation_keeps_provenance) :-
    explain_task(normalize_terms, Explanation),
    assertion(Explanation ==
              explanation(task(normalize_terms),
                          supports([
                              fact(task(normalize_terms, ben, ready,
                                        [prolog, validation]),
                                   source(book_fixture,
                                          task_normalize_terms))
                          ]))).

test(dependency_explanation_keeps_each_support) :-
    explain_dependency(check_constraints, collect_sources, Explanation),
    assertion(Explanation ==
              explanation(dependency(check_constraints, collect_sources),
                          path([check_constraints,
                                normalize_terms,
                                collect_sources]),
                          supports([
                              fact(depends_on(check_constraints,
                                              normalize_terms),
                                   source(book_fixture,
                                          dep_constraints_normalize)),
                              fact(depends_on(normalize_terms,
                                              collect_sources),
                                   source(book_fixture,
                                          dep_normalize_collect))
                          ]))).

test(sound_unification_rejects_self_containment, [fail]) :-
    unify_with_occurs_check(X, wrapper(X)).

test(swi_default_unification_can_form_a_cyclic_term) :-
    X = wrapper(X),
    assertion(cyclic_term(X)).

:- end_tests(relational_task_solver).
