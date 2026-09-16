:- begin_tests(relational_task_solver).

:- use_module(task_solver).
:- use_module(task_report).
:- use_module(library(time)).

:- multifile relational_task_solver:dependency_record/3.

% Test-local graph fixture. These clauses extend the solver's private
% dependency relation only while this test file is loaded; production book
% fixture data remains unchanged.
relational_task_solver:dependency_record(cycle_probe_a, cycle_probe_b,
                  source(test_fixture, dep_cycle_a_b)).
relational_task_solver:dependency_record(cycle_probe_b, cycle_probe_a,
                  source(test_fixture, dep_cycle_b_a)).

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

test(list_relation_finds_tag_once) :-
    findall(true,
            has_tag(write_explanation, explanation),
            Matches),
    assertion(Matches == [true]).

test(active_tasks_are_relational) :-
    setof(Task, owned_active_task(lina, Task),
          [publish_report, write_explanation]).

test(ready_tasks_expose_all_choice_point_answers,
     all(Task-Owner == [collect_sources-ada,
                        normalize_terms-ben,
                        write_explanation-lina])) :-
    ready_task(Task, Owner).

test(first_ready_task_commits_to_current_program_order) :-
    first_ready_task(Task, Owner),
    assertion(Task-Owner == collect_sources-ada).

test(consumer_module_composes_only_exported_project_api) :-
    ready_report(normalize_terms, Owner, Explanation),
    assertion(Owner == ben),
    assertion(Explanation ==
              explanation(task(normalize_terms),
                          supports([
                              fact(task(normalize_terms, ben, ready,
                                        [prolog, validation]),
                                   source(book_fixture,
                                          task_normalize_terms))
                          ]))).

test(direct_dependency_path_is_unique_in_fixture) :-
    findall(Path,
            dependency_path(normalize_terms, collect_sources, Path),
            Paths),
    assertion(Paths == [[normalize_terms, collect_sources]]).

test(transitive_dependency_path_is_unique_in_fixture) :-
    findall(Path,
            dependency_path(publish_report, collect_sources, Path),
            Paths),
    assertion(Paths == [[publish_report,
                         write_explanation,
                         check_constraints,
                         normalize_terms,
                         collect_sources]]).

test(missing_dependency_path_fails, [fail]) :-
    dependency_path(collect_sources, publish_report, _).

test(cyclic_dependency_graph_terminates_for_unreachable_target) :-
    assertion(depends_on(cycle_probe_a, cycle_probe_b)),
    assertion(depends_on(cycle_probe_b, cycle_probe_a)),
    call_with_time_limit(
        1,
        findall(Path,
                dependency_path(cycle_probe_a, unreachable_target, Path),
                Paths)),
    assertion(Paths == []).

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

test(dependency_explanation_is_unique_and_keeps_each_support) :-
    findall(Explanation,
            explain_dependency(check_constraints,
                               collect_sources,
                               Explanation),
            Explanations),
    assertion(Explanations ==
              [explanation(dependency(check_constraints, collect_sources),
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
                           ]))]).

test(sound_unification_rejects_self_containment, [fail]) :-
    unify_with_occurs_check(X, wrapper(X)).

test(swi_default_unification_can_form_a_cyclic_term) :-
    X = wrapper(X),
    assertion(cyclic_term(X)).

:- end_tests(relational_task_solver).
