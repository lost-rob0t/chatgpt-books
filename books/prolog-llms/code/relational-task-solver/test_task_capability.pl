:- begin_tests(task_capability).

:- use_module(task_capability).

test(closed_capability_vocabulary) :-
    findall(Name/Arity, capability(Name, Arity), Capabilities),
    Capabilities ==
        [ tasks_by_owner/1,
          tasks_by_status/1,
          tasks_by_tag/1,
          dependency_path/2
        ].

test(one_argument_capability_uses_trusted_handler) :-
    execute_capability(
        request(tasks_by_owner, [ada]),
        [ result(task(collect_sources), owner(ada), status(ready),
                 tags([research,prolog])),
          result(task(check_constraints), owner(ada), status(blocked),
                 tags([prolog,validation]))
        ]).

test(two_argument_capability_uses_trusted_handler) :-
    execute_capability(
        request(dependency_path, [publish_report, collect_sources]),
        [path([publish_report, write_explanation, check_constraints,
               normalize_terms, collect_sources])]).

test(unknown_capability_is_rejected, [fail]) :-
    execute_capability(request(halt, [now]), _).

test(wrong_capability_arity_is_rejected, [fail]) :-
    execute_capability(request(tasks_by_owner, [ada, extra]), _).

test(callable_looking_atom_remains_plain_data) :-
    execute_capability(request(tasks_by_owner, [halt]), []).

test(callable_term_argument_is_rejected, [fail]) :-
    execute_capability(request(tasks_by_owner, [call(halt)]), _).

test(reflection_describes_without_authorizing_execution) :-
    describe_term(call(halt), term_shape(call/1, [halt])),
    \+ execute_capability(request(call, [halt]), _).

test(malformed_request_shape_is_rejected, [fail]) :-
    execute_capability(call(halt), _).

:- end_tests(task_capability).
