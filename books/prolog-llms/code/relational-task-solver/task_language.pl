:- module(task_language,
          [ parse_task_command/2,
            parse_task_command_prefix/3,
            execute_task_command/2,
            task_command//1
          ]).

:- use_module(library(error), [must_be/2]).
:- use_module(task_solver,
              [ task/4,
                has_tag/2,
                dependency_path/3
              ]).

/** <module> Closed task-command language -- Project 1, milestone C

This module keeps parsing and execution separate.  The DCG can only construct a
small closed vocabulary of data terms.  execute_task_command/2 then dispatches
those terms through explicit clauses to the relational task solver.  Input
atoms never become predicate names and this module does not use call/1.
*/

%!  parse_task_command(+Tokens:list(atom), -Command) is semidet.
%
%   Parse one complete command.  phrase/2 requires the grammar to consume the
%   full token list.
parse_task_command(Tokens, Command) :-
    token_list(Tokens),
    phrase(task_command(Command), Tokens).

%!  parse_task_command_prefix(+Tokens:list(atom), -Command, -Rest) is semidet.
%
%   Parse one command prefix and expose the unconsumed tokens.  This exists to
%   make phrase/3 remainder semantics explicit in the teaching material; the
%   normal public command boundary is parse_task_command/2.
parse_task_command_prefix(Tokens, Command, Rest) :-
    token_list(Tokens),
    phrase(task_command(Command), Tokens, Rest).

token_list(Tokens) :-
    must_be(list, Tokens),
    atom_tokens(Tokens).

atom_tokens([]).
atom_tokens([Token|Rest]) :-
    must_be(atom, Token),
    atom_tokens(Rest).

% Closed grammar.  The output is data, not a callable goal.
task_command(tasks(owner(Owner))) -->
    [tasks, owned, by],
    identifier(Owner).
task_command(tasks(status(Status))) -->
    [tasks, with, status],
    identifier(Status).
task_command(tasks(tag(Tag))) -->
    [tasks, tagged],
    identifier(Tag).
task_command(dependency_path(Task, Dependency)) -->
    [dependency, path, from],
    identifier(Task),
    [to],
    identifier(Dependency).

identifier(Value) -->
    [Value],
    { atom(Value) }.

%!  execute_task_command(+Command, -Results) is semidet.
%
%   Execute only the closed AST forms defined above.  Unknown terms fail
%   instead of being meta-called.  Results remain ordinary structured data.
execute_task_command(tasks(owner(Owner)), Results) :-
    must_be(atom, Owner),
    findall(result(task(Task), owner(Owner), status(Status), tags(Tags)),
            task(Task, Owner, Status, Tags),
            Results).
execute_task_command(tasks(status(Status)), Results) :-
    must_be(atom, Status),
    findall(result(task(Task), owner(Owner), status(Status), tags(Tags)),
            task(Task, Owner, Status, Tags),
            Results).
execute_task_command(tasks(tag(Tag)), Results) :-
    must_be(atom, Tag),
    findall(result(task(Task), owner(Owner), status(Status), tags(Tags)),
            ( task(Task, Owner, Status, Tags),
              has_tag(Task, Tag)
            ),
            Results).
execute_task_command(dependency_path(Task, Dependency), Results) :-
    must_be(atom, Task),
    must_be(atom, Dependency),
    findall(path(Path),
            dependency_path(Task, Dependency, Path),
            Results).
