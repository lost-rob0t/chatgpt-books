:- module(relational_task_solver,
          [ task/4,
            depends_on/2,
            has_tag/2,
            owned_active_task/2,
            dependency_path/3,
            explain_task/2,
            explain_dependency/3
          ]).

/** <module> Relational Task Solver -- Project 1, milestone A

A deliberately small, deterministic symbolic baseline for the opening
chapters of _Prolog + LLMs_.  All data below is synthetic book fixture data.
No model or external service participates in any result.
*/

% task_record(Id, Owner, Status, Tags, Provenance).
task_record(collect_sources, ada, ready, [research,prolog],
            source(book_fixture, task_collect_sources)).
task_record(normalize_terms, ben, ready, [prolog,validation],
            source(book_fixture, task_normalize_terms)).
task_record(check_constraints, ada, blocked, [prolog,validation],
            source(book_fixture, task_check_constraints)).
task_record(write_explanation, lina, ready, [prolog,explanation],
            source(book_fixture, task_write_explanation)).
task_record(publish_report, lina, planned, [report,explanation],
            source(book_fixture, task_publish_report)).

% dependency_record(Task, Dependency, Provenance).
dependency_record(normalize_terms, collect_sources,
                  source(book_fixture, dep_normalize_collect)).
dependency_record(check_constraints, normalize_terms,
                  source(book_fixture, dep_constraints_normalize)).
dependency_record(write_explanation, check_constraints,
                  source(book_fixture, dep_explanation_constraints)).
dependency_record(publish_report, write_explanation,
                  source(book_fixture, dep_publish_explanation)).

task(Id, Owner, Status, Tags) :-
    task_record(Id, Owner, Status, Tags, _).

depends_on(Task, Dependency) :-
    dependency_record(Task, Dependency, _).

has_tag(Task, Tag) :-
    task(Task, _, _, Tags),
    list_contains(Tag, Tags).

owned_active_task(Owner, Task) :-
    task(Task, Owner, Status, _),
    dif(Status, done).

% A small list relation is kept explicit for the course instead of hiding the
% mechanism behind member/2 in the first milestone.
list_contains(Item, [Item|_]).
list_contains(Item, [_|Rest]) :-
    list_contains(Item, Rest).

% dependency_path(+Task, +Dependency, -Path)
% Path is cycle-safe for finite dependency graphs: a task already on the
% current search branch is not revisited.
dependency_path(Task, Dependency, Path) :-
    dependency_path_(Task, Dependency, [Task], Path).

dependency_path_(Task, Dependency, _, [Task, Dependency]) :-
    depends_on(Task, Dependency).
dependency_path_(Task, Dependency, Seen, [Task|Rest]) :-
    depends_on(Task, Next),
    dif(Next, Dependency),
    \+ list_contains(Next, Seen),
    dependency_path_(Next, Dependency, [Next|Seen], Rest).

explain_task(Task, Explanation) :-
    task_record(Task, Owner, Status, Tags, Source),
    Explanation = explanation(
                      task(Task),
                      supports([
                          fact(task(Task, Owner, Status, Tags), Source)
                      ])
                  ).

explain_dependency(Task, Dependency, Explanation) :-
    dependency_path(Task, Dependency, Path),
    path_sources(Path, Supports),
    Explanation = explanation(
                      dependency(Task, Dependency),
                      path(Path),
                      supports(Supports)
                  ).

path_sources([_], []).
path_sources([Task, Dependency|Rest],
             [fact(depends_on(Task, Dependency), Source)|Supports]) :-
    dependency_record(Task, Dependency, Source),
    path_sources([Dependency|Rest], Supports).
