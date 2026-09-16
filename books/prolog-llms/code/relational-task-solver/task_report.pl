:- module(task_report,
          [ ready_report/3
          ]).

:- use_module(task_solver,
              [ ready_task/2,
                explain_task/2
              ]).

/** <module> Project 1 consumer module

A small second module used by the book to demonstrate explicit module imports.
It composes only exported predicates from relational_task_solver.  This is an
interface/namespace boundary for maintainability, not a security sandbox.
*/

ready_report(Task, Owner, Explanation) :-
    ready_task(Task, Owner),
    explain_task(Task, Explanation).
