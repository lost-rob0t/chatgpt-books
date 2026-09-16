:- module(task_schedule,
          [ schedule_constraints/2,
            first_minimum_schedule/2,
            deadline_flag/3
          ]).

:- use_module(library(clpfd)).

/** <module> Project 1 scheduling worksheet

A synthetic, model-free CLP(FD) worksheet used by Chapter 6 of
_Prolog + LLMs_.  It is intentionally separate from task_solver.pl: these are
scheduling requirements for a worked exercise, not additional task facts.

The core schedule_constraints/2 relation only posts constraints.  Search is an
explicit later step.  first_minimum_schedule/2 is named for its commitment: it
uses once/1 around optimization labeling and therefore returns one first
minimum-makespan schedule in the current labeling order.
*/

% schedule_constraints(-Schedule, -Makespan)
% Schedule is a fixed-shape worksheet whose starts remain CLP(FD) variables
% until the caller chooses a labeling/search policy.
schedule_constraints(Schedule, Makespan) :-
    Schedule = [ slot(collect_sources, Collect, 2),
                 slot(normalize_terms, Normalize, 2),
                 slot(validate_schema, Validate, 2),
                 slot(verify_provenance, Verify, 3),
                 slot(publish_report, Publish, 1)
               ],
    Starts = [Collect, Normalize, Validate, Verify, Publish],
    Starts ins 0..12,

    % Precedence: collection -> normalization -> both verification jobs ->
    % publication.  verify_provenance additionally has a release time of 5.
    Normalize #>= Collect + 2,
    Validate  #>= Normalize + 2,
    Verify    #>= Normalize + 2,
    Verify    #>= 5,
    Publish   #>= Validate + 2,
    Publish   #>= Verify + 3,

    % validate_schema and verify_provenance share one verifier.  They may run
    % in either order, but their half-open execution intervals may not overlap.
    nonoverlap(Validate, 2, Verify, 3),

    Makespan #= Publish + 1.

% first_minimum_schedule(-Schedule, -Makespan)
% labeling([min(Makespan)], ...) enumerates solutions by increasing objective.
% This wrapper deliberately commits to the first such solution.  The core
% constraint relation remains separately available so alternate/equally-optimal
% schedules can be studied without this commitment.
first_minimum_schedule(Schedule, Makespan) :-
    schedule_constraints(Schedule, Makespan),
    schedule_starts(Schedule, Starts),
    once(labeling([ffc, min(Makespan)], Starts)).

% deadline_flag(+Makespan, +Deadline, -Late)
% Reification turns the truth of a finite-domain constraint into explicit data:
% Late = 1 iff Makespan is strictly after Deadline, otherwise Late = 0.
deadline_flag(Makespan, Deadline, Late) :-
    Late in 0..1,
    (Makespan #> Deadline) #<==> Late.

nonoverlap(StartA, DurationA, StartB, DurationB) :-
    (StartA + DurationA #=< StartB) #\/
    (StartB + DurationB #=< StartA).

schedule_starts([], []).
schedule_starts([slot(_, Start, _)|Slots], [Start|Starts]) :-
    schedule_starts(Slots, Starts).
