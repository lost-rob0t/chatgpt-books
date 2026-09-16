:- module(task_capability,
          [ capability/2,
            execute_capability/2,
            describe_term/2
          ]).

:- use_module(task_language, [execute_task_command/2]).

/** <module> Closed capability dispatch -- Project 1, milestone E

A request is data.  This module grants execution authority only after a request
matches a closed capability tag, has the exact authored arity, and contains
atom arguments.  The selected handler is repository-authored code; request data
never supplies a predicate name or callable goal.
*/

%!  capability(?Name:atom, ?Arity:nonneg) is nondet.
%
%   Enumerate the complete public capability vocabulary.  This relation is
%   backed by explicit facts, not current_predicate/1 or runtime reflection.
capability(Name, Arity) :-
    capability_handler(Name, Arity, _).

%!  execute_capability(+Request, -Results) is semidet.
%
%   Execute one closed request of the form request(Tag, Arguments).  Arguments
%   must be a proper list of atoms with exactly the declared capability arity.
%   Only the trusted handler selected below is meta-called.
execute_capability(request(Name, Arguments), Results) :-
    atom(Name),
    proper_atom_list(Arguments),
    capability_handler(Name, Arity, Handler),
    exact_arity(Arguments, Arity),
    call_handler(Arity, Handler, Arguments, Results).

%!  describe_term(+Term, -Description) is semidet.
%
%   Describe a compound term as data.  Decomposition does not grant permission
%   to execute the described term.
describe_term(Term, term_shape(Name/Arity, Arguments)) :-
    nonvar(Term),
    compound(Term),
    compound_name_arguments(Term, Name, Arguments),
    length(Arguments, Arity).

capability_handler(tasks_by_owner, 1, run_tasks_by_owner).
capability_handler(tasks_by_status, 1, run_tasks_by_status).
capability_handler(tasks_by_tag, 1, run_tasks_by_tag).
capability_handler(dependency_path, 2, run_dependency_path).

call_handler(1, Handler, [Argument], Results) :-
    call(Handler, Argument, Results).
call_handler(2, Handler, [Left, Right], Results) :-
    call(Handler, Left, Right, Results).

run_tasks_by_owner(Owner, Results) :-
    execute_task_command(tasks(owner(Owner)), Results).
run_tasks_by_status(Status, Results) :-
    execute_task_command(tasks(status(Status)), Results).
run_tasks_by_tag(Tag, Results) :-
    execute_task_command(tasks(tag(Tag)), Results).
run_dependency_path(Task, Dependency, Results) :-
    execute_task_command(dependency_path(Task, Dependency), Results).

proper_atom_list([]).
proper_atom_list([Argument|Rest]) :-
    atom(Argument),
    proper_atom_list(Rest).

exact_arity([], 0).
exact_arity([_|Rest], Arity) :-
    Arity > 0,
    Next is Arity - 1,
    exact_arity(Rest, Next).
