% Project 1: Relational Query System — milestone 1.
% Synthetic data only.  The predicates are intentionally small enough to inspect.

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
