% Project 1: Relational Query System.
% Synthetic data only. The predicates are intentionally small enough to inspect.

person(ada).
person(ben).
person(lina).
person(noor).
person(sam).

lives_in(ada, harbor).
lives_in(lina, harbor).
lives_in(ben, orchard).
lives_in(noor, orchard).
lives_in(sam, summit).

mentor(ada, lina).
mentor(noor, ben).
mentor(sam, ada).

works_on(ada, atlas).
works_on(lina, atlas).
works_on(ben, beacon).
works_on(noor, beacon).
works_on(noor, atlas).
works_on(sam, compass).

% Milestone 2 adds list-shaped profile data and a deliberately cyclic graph.
topics(ada, [prolog, systems, debugging]).
topics(lina, [prolog, testing]).
topics(ben, [testing, databases]).
topics(noor, [logic, systems]).
topics(sam, [erlang, systems]).

follows(ada, lina).
follows(ada, noor).
follows(lina, noor).
follows(lina, ben).
follows(noor, ada).      % Deliberate cycle: ada -> ... -> noor -> ada.
follows(noor, ben).
follows(ben, sam).

same_neighborhood(Person, Other) :-
    lives_in(Person, Place),
    lives_in(Other, Place),
    dif(Person, Other).

project_peer(Person, Other, Project) :-
    works_on(Person, Project),
    works_on(Other, Project),
    dif(Person, Other).

mentor_of(Mentor, Student) :-
    mentor(Mentor, Student).

% A list relation derived from list shape before library(lists) is introduced.
topic_member(Topic, [Topic|_]).
topic_member(Topic, [_|Rest]) :-
    topic_member(Topic, Rest).

interested_in(Person, Topic) :-
    topics(Person, Topics),
    topic_member(Topic, Topics).

% Tail-recursive reversal used internally by the path relation.
list_reverse(List, Reversed) :-
    list_reverse_(List, [], Reversed).

list_reverse_([], Accumulator, Accumulator).
list_reverse_([Head|Tail], Accumulator, Reversed) :-
    list_reverse_(Tail, [Head|Accumulator], Reversed).

% Succeeds when Term differs from every element in a finite list.
% dif/2 keeps the relation explicit; this is not negation-as-failure.
different_from_all(_, []).
different_from_all(Term, [Seen|Rest]) :-
    dif(Term, Seen),
    different_from_all(Term, Rest).

% Enumerate simple directed paths. Seen is branch-local search state, not
% persistent application state. The public path is returned start -> goal.
connection_path(Start, Goal, Path) :-
    dif(Start, Goal),
    connection_path_(Start, Goal, [Start], ReversedPath),
    list_reverse(ReversedPath, Path).

connection_path_(Current, Goal, Seen, [Goal|Seen]) :-
    follows(Current, Goal),
    different_from_all(Goal, Seen).
connection_path_(Current, Goal, Seen, Path) :-
    follows(Current, Next),
    different_from_all(Next, Seen),
    connection_path_(Next, Goal, [Next|Seen], Path).

% Deliberately commits to the first proof produced by connection_path/3.
% The underlying relation remains nondeterministic.
first_connection_path(Start, Goal, Path) :-
    once(connection_path(Start, Goal, Path)).

% Chapter 7 arithmetic contract: path_hops(+Path, -Hops).
% Path is expected to be a finite, proper, non-empty path list.  This
% intentionally uses low-level arithmetic evaluation so its mode boundary is
% visible before later CLP(FD) chapters introduce relational integer constraints.
path_hops([_], 0).
path_hops([_|Tail], Hops) :-
    Tail = [_|_],
    path_hops(Tail, TailHops),
    Hops is TailHops + 1.

% Preserve the underlying path relation and attach a derived numeric property.
% This is path annotation, not shortest-path search.
connection_with_hops(Start, Goal, Path, Hops) :-
    connection_path(Start, Goal, Path),
    path_hops(Path, Hops).

% Supported teaching mode: connection_within_hops(+Start,+Goal,+Limit,-Path,-Hops).
% Limit must already be numeric because =</2 evaluates both arithmetic operands.
connection_within_hops(Start, Goal, Limit, Path, Hops) :-
    connection_with_hops(Start, Goal, Path, Hops),
    Hops =< Limit.
