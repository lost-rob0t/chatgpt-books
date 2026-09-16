:- begin_tests(task_language).

:- use_module(task_language).

test(parse_owner_command) :-
    parse_task_command([tasks, owned, by, ada],
                       tasks(owner(ada))).

test(parse_status_command) :-
    parse_task_command([tasks, with, status, ready],
                       tasks(status(ready))).

test(parse_tag_command) :-
    parse_task_command([tasks, tagged, validation],
                       tasks(tag(validation))).

test(parse_dependency_command) :-
    parse_task_command([dependency, path, from, publish_report,
                        to, collect_sources],
                       dependency_path(publish_report, collect_sources)).

test(unknown_command_is_rejected, [fail]) :-
    parse_task_command([call, halt], _).

test(malformed_command_is_rejected, [fail]) :-
    parse_task_command([tasks, owned, ada], _).

test(full_parse_rejects_unconsumed_tokens, [fail]) :-
    parse_task_command([tasks, tagged, prolog, trailing], _).

test(prefix_parse_exposes_remainder) :-
    parse_task_command_prefix([tasks, tagged, prolog, trailing, tokens],
                              tasks(tag(prolog)),
                              [trailing, tokens]).

test(owner_dispatch_uses_allowlisted_relation) :-
    execute_task_command(
        tasks(owner(ada)),
        [ result(task(collect_sources), owner(ada), status(ready),
                 tags([research,prolog])),
          result(task(check_constraints), owner(ada), status(blocked),
                 tags([prolog,validation]))
        ]).

test(status_dispatch_returns_all_matching_tasks) :-
    execute_task_command(
        tasks(status(ready)),
        [ result(task(collect_sources), owner(ada), status(ready),
                 tags([research,prolog])),
          result(task(normalize_terms), owner(ben), status(ready),
                 tags([prolog,validation])),
          result(task(write_explanation), owner(lina), status(ready),
                 tags([prolog,explanation]))
        ]).

test(tag_dispatch_returns_structured_results) :-
    execute_task_command(
        tasks(tag(validation)),
        [ result(task(normalize_terms), owner(ben), status(ready),
                 tags([prolog,validation])),
          result(task(check_constraints), owner(ada), status(blocked),
                 tags([prolog,validation]))
        ]).

test(dependency_dispatch_returns_path) :-
    execute_task_command(
        dependency_path(publish_report, collect_sources),
        [path([publish_report, write_explanation, check_constraints,
               normalize_terms, collect_sources])]).

test(arbitrary_callable_term_is_not_dispatched, [fail]) :-
    execute_task_command(call(halt), _).

test(parsed_ast_is_data_until_explicit_dispatch) :-
    parse_task_command([tasks, tagged, explanation], Command),
    Command == tasks(tag(explanation)),
    execute_task_command(Command, Results),
    Results ==
        [ result(task(write_explanation), owner(lina), status(ready),
                 tags([prolog,explanation])),
          result(task(publish_report), owner(lina), status(planned),
                 tags([report,explanation]))
        ].

:- end_tests(task_language).
