#+title: Prolog for Beginners: Thinking in Relations
:PROPERTIES:
:ID:       b500381b-81f9-5eff-8f05-56fd2f860f8a
:END:
#+bibliography: ../references.bib

* How to use this book
This book teaches Prolog as a way to describe and investigate *relations*. It is not a catalog of punctuation. You will keep returning to a small set of runnable systems, break them on purpose, inspect the resulting search, and then make them more capable.

Examples target SWI-Prolog. When a behavior is specific to SWI-Prolog rather than a safe general Prolog idea, the text says so. On 2026-09-16 the official stable channel lists SWI-Prolog 10.0.2 [cite:@swi-stable-download]. The exact interpreter used for a tested result is recorded with the test evidence rather than silently assumed.

The first project begins now. By the end of these opening chapters you will already have a knowledge base, derived relations, executable tests, and a mental model of unification strong enough to debug wrong answers instead of cargo-culting query syntax.

* Chapter 1 -- A Program You Ask Questions
:PROPERTIES:
:ID:       51201d13-4679-4d67-969a-b448b123dcf2
:END:

** 1.1 Start with a relation, not a procedure
Suppose we know that Ada and Lina live in Harbor, Ben and Noor live in Orchard, and several people work on projects. In a conventional first programming exercise you might reach immediately for a class, a dictionary, a loop, or a SQL table. In Prolog, start one level simpler: state relations that hold.

#+begin_src prolog
person(ada).
person(lina).
lives_in(ada, harbor).
lives_in(lina, harbor).
works_on(ada, atlas).
works_on(lina, atlas).
#+end_src

A line such as =lives_in(ada, harbor).= is a *fact*. Read it as “the relation =lives_in/2= holds between =ada= and =harbor=.” The =/2= in the prose is not division. It is the conventional predicate indicator: name plus arity, where arity is the number of arguments.

This apparently fussy wording pays rent later. We have not said that =ada= is an object with a =lives_in= field. We have not said that Harbor contains a list of people. We have described one relation and can ask it in more than one direction.

** 1.2 Queries are questions with possible bindings
With the file loaded, ask:

#+begin_src prolog
?- lives_in(ada, harbor).
#+end_src

That is a yes/no question: can Prolog establish this goal from the clauses it knows? Now replace one position with a variable:

#+begin_src prolog
?- lives_in(Who, harbor).
#+end_src

The question is no longer merely “is this true?” It asks for substitutions for =Who= that make the goal true. A top level can offer another solution when more than one proof/binding exists. SWI-Prolog's basic load/query workflow is documented in its quick-start manual [cite:@swi-quickstart].

This is the first habit to build: before writing a predicate, write down several modes of question you hope it can answer. For =lives_in/2= we already care about at least these:

#+begin_example
lives_in(ada, harbor).      % verify a complete claim
lives_in(Who, harbor).      % find people in one place
lives_in(ada, Where).       % find Ada's place
lives_in(Who, Where).       % enumerate known person/place pairs
#+end_example

Do not infer from this that every Prolog predicate works usefully in every direction. That is something we test, not a magical language guarantee. But thinking in relations makes directionality an explicit design question instead of an accident.

** 1.3 Rules derive relations from relations
Facts are useful, but the point is not to type every answer by hand. We can define a relation for people who share a neighborhood:

#+begin_src prolog
same_neighborhood(Person, Other) :-
    lives_in(Person, Place),
    lives_in(Other, Place),
    dif(Person, Other).
#+end_src

Read =:-= as “if” for now. Read the comma as conjunction: all goals in the body must succeed for the rule to establish its head. So two people share a neighborhood if there is a =Place= in which both live and the two people are different.

The variable =Place= is not an assignment slot whose value changes as the rule runs. It is a logical variable shared by both body goals. The same variable appearing twice requires those positions to agree on one term. Chapter 3 will make that operation precise.

Why use =dif/2= here instead of pretending two names are always different? Because the relation should explicitly say what excludes self-pairs. We are not yet teaching negation or cut; we are stating a disequality constraint at the point it belongs.

** 1.4 Clause order is not the meaning, but execution has an order
Prolog is declarative enough that we can read the previous rule as a logical statement. It is also an executable language. SWI-Prolog tries clauses/goals according to its execution strategy and may leave choice points for alternatives. You do not need to master the machinery on page one, but you should notice an important tension that will drive the whole book:

- the *declarative reading* asks what relation the clauses describe;
- the *operational reading* asks how the engine searches for solutions.

Good Prolog programmers learn to hold both views. Chapters 4, 8, 9, 17, and 20 will progressively expose backtracking, control, tabling, and performance. We will not smuggle those topics into a vague phrase like “Prolog figures it out.”

** 1.5 Failure is data about a goal
Consider the directed relation:

#+begin_src prolog
mentor(ada, lina).
#+end_src

The query =mentor(ada, lina)= succeeds. The reversed query =mentor(lina, ada)= does not become true merely because English can describe mentoring as a relationship. Predicate argument order is part of the model.

This yields the first debugging discipline:

1. Say the predicate aloud with argument roles: =mentor(Mentor, Student)=.
2. Check the concrete facts.
3. Reduce a failing derived query to the smaller goals in its rule body.
4. Only then blame “backtracking.”

Most beginner bugs are not mysterious search problems. They are malformed terms, wrong argument roles, accidentally unshared variables, or relations whose clauses do not say what the author thought they said.

** 1.6 Lab -- interrogate the community graph
The canonical project source for this milestone is =books/prolog/code/relational-query/community.pl=. Load it with SWI-Prolog and answer these without editing the data first:

1. Which people live in =orchard=?
2. Which projects does Noor work on?
3. Who shares a neighborhood with Ada?
4. Who is a project peer of Ada, and on which project?
5. Which person both mentors Lina and works on Atlas?

Then make three predictions before asking Prolog:

- Does =mentor_of(lina, ada)= succeed?
- Does =same_neighborhood(ada, ada)= succeed?
- How many answers does =project_peer(ada, Other, Project)= have?

The point is not merely to get the answers. Write down *which clauses* are sufficient to establish or reject each goal.

** 1.7 Break it deliberately
Make a temporary copy and introduce each defect separately:

- Change =harbor= to =Harbor= in one fact.
- Swap the arguments of one =mentor/2= fact.
- Remove the period after a fact.
- Misspell one occurrence of =works_on=.

For each breakage, classify the outcome before fixing it: syntax error, warning, clean failure, or surprising extra success. This habit—predict, run, explain—will matter more than memorizing error messages.

* Chapter 2 -- Terms, Variables, and Shape
:PROPERTIES:
:ID:       9b19e82b-17ac-490a-a5c1-7be327882d96
:END:

** 2.1 Almost everything you manipulate is a term
Prolog programs gain much of their flexibility from a small structural vocabulary. The examples below are terms:

#+begin_src prolog
ada
42
Person
project(atlas)
assignment(ada, project(atlas))
edge(ada, lina, mentor)
#+end_src

For now, separate them into four useful beginner categories:

- *variables* stand for terms and begin with an uppercase letter or underscore under the default syntax;
- *atoms* are symbolic constants such as =ada=, =atlas=, and =mentor=;
- *numbers* are numeric terms;
- *compound terms* have a functor and arguments, such as =project(atlas)= and =edge(ada,lina,mentor)=.

A compound term is data. It does not automatically call a function. The term =project(atlas)= can sit inside another term, be unified with a pattern, stored as an argument, or later interpreted by a predicate. This “code-shaped data” becomes extremely important when we reach DCGs and meta-programming.

** 2.2 Capitalization is semantic
Under the default syntax used in this book, =ada= is an atom and =Ada= is a variable. SWI-Prolog also supports a non-default, per-module =var_prefix= mode in which only underscore introduces a variable; that is an implementation option, not the syntax this course uses [cite:@swi-syntax].

This means a typo can change *kind*, not just spelling:

#+begin_src prolog
?- lives_in(ada, harbor).
?- lives_in(Ada, harbor).
#+end_src

The first asks whether a particular person lives in Harbor. The second asks for a person and names the answer variable =Ada=. If you intended a constant, the second query is a bug that can look like a suspiciously successful test.

Debugging exercise: write one PL-Unit test that would fail if a specific constant were accidentally replaced by a fresh variable. Tests should protect meaning, not merely execute lines.

** 2.3 Sharing a variable creates a constraint of agreement
Compare:

#+begin_src prolog
?- lives_in(Person, Place), works_on(Person, Project).
#+end_src

with:

#+begin_src prolog
?- lives_in(Person, Place), works_on(Other, Project).
#+end_src

In the first query, both goals share =Person=. An answer must describe one person who satisfies both relations. In the second, the people may differ because =Person= and =Other= are distinct variables.

This is one of the biggest conceptual jumps for programmers coming from assignment-heavy languages. Reusing a variable is not “reading the latest value.” It expresses identity: those positions refer to the same logical unknown.

** 2.4 The anonymous variable means “I do not care about this binding”
The variable written =_= is special. Each occurrence is a distinct anonymous variable. The SWI-Prolog FAQ makes this explicit [cite:@swi-singleton-faq]. Therefore:

#+begin_src prolog
?- works_on(_, atlas), mentor(_, _).
#+end_src

does *not* require the person in the first goal to be the mentor or student in the second. If you need sharing, use a named variable:

#+begin_src prolog
?- works_on(Person, atlas), mentor(Person, _).
#+end_src

An underscore-prefixed *named* variable such as =_Person= is different from bare =_=. Repeating =_Person= repeats the same variable. Use the bare anonymous variable when a position truly does not matter to the relation you are expressing. Do not use it to hide confusion about what a predicate's arguments mean.

** 2.5 Atoms are not SWI strings
Our early project uses atoms for symbolic identifiers:

#+begin_src prolog
harbor
atlas
ada
#+end_src

It does not use:

#+begin_src prolog
"harbor"
#+end_src

as a drop-in spelling variant. SWI-SPECIFIC: since SWI-Prolog 7, double-quoted text is by default a distinct =string= value [cite:@swi-strings]. Strings, atoms, and lists of character codes serve different purposes. We will treat text representation seriously in the DCG chapters. For now, symbolic entities in the knowledge graph are atoms.

Debugging exercise: ask both =lives_in(ada, harbor)= and =lives_in(ada, "harbor")=. Explain the difference in terms of the term types, not typography.

** 2.6 Compound terms let the data acquire structure
Instead of inventing a new flat atom such as =atlas_project=, we can construct terms:

#+begin_src prolog
project(atlas)
role(mentor, ada, lina)
location(city(harbor), country(exampleland))
#+end_src

Their shape can itself be queried through unification. That lets a project evolve from a flat set of constants toward structured domain data without abandoning the relational model.

Do not overdo it yet. Deeply nested terms are not automatically “more Prolog.” The right representation is the one that makes the relations you need clear and testable.

** 2.7 Exercises
1. Label every subterm in =assignment(ada, project(atlas))= as atom, variable, number, or compound term where applicable.
2. Predict whether =edge(X, X)= can unify with =edge(ada, lina)=. Explain before running it.
3. Rewrite a query that uses two anonymous variables so that it instead requires both positions to contain the same term.
4. Construct a query over the community graph that returns a person's neighborhood and project in one answer.
5. Debug this intended constant: =lives_in(Person, Harbor)=. What question did it actually ask?

* Chapter 3 -- Unification: Making Terms Agree
:PROPERTIES:
:ID:       14805a94-5bcf-4994-8424-b767e7fd04d8
:END:

** 3.1 The engine is not doing string matching
When a goal encounters a clause, Prolog needs to determine whether relevant terms can be made the same by binding variables consistently. That operation is *unification*.

SWI-Prolog exposes ordinary unification directly as =(/2)= and also uses unification implicitly when a goal matches a clause head [cite:@swi-unification]. Start with finite terms:

#+begin_example
X = ada
pair(X, lina) = pair(ada, Y)
project(Name) = project(atlas)
#+end_example

Work them mechanically:

- =X = ada= can succeed with =X= bound to =ada=.
- =pair(X,lina) = pair(ada,Y)= first requires the functor/arity to agree, then corresponding arguments to agree, yielding =X = ada= and =Y = lina=.
- =project(Name) = project(atlas)= yields =Name = atlas=.

Now compare cases that cannot be made equal:

#+begin_example
ada = lina
pair(ada) = pair(ada, lina)
project(atlas) = person(atlas)
pair(X, X) = pair(ada, lina)
#+end_example

The last is especially important. The first occurrence of =X= can agree with =ada=, but then the second occurrence is constrained to that same term and cannot also agree with =lina=.

** 3.2 A substitution is global to the current logical branch
Within a successful branch of a query, a variable binding constrains every occurrence of that variable. Consider the Project 1 test:

#+begin_src prolog
mentor_of(Person, lina),
works_on(Person, atlas).
#+end_src

The first goal can bind =Person= to =ada=. The second goal is then not asking for any Atlas contributor; it asks whether that same =ada= works on Atlas. The shared variable is the join.

If you come from SQL, “join” is a useful analogy. If you come from functional programming, pattern matching is a useful analogy. Neither is the whole story: Prolog unification is symmetric at the term level and can bind variables on either side.

** 3.3 Trace unification by hand before reaching for the debugger
For the first dozen exercises, use a substitution table:

#+begin_example
Goal: edge(X, project(P)) = edge(ada, project(atlas))

Step                         Required binding
edge/2 matches edge/2        --
X matches ada                X = ada
project/1 matches project/1  --
P matches atlas              P = atlas

Result: succeeds with {X=ada, P=atlas}
#+end_example

Now do the same for:

#+begin_example
assignment(Person, project(Project), Person)
=
assignment(ada, project(atlas), lina)
#+end_example

The failure is not because Prolog “chose wrong.” The repeated =Person= imposes an equality that the concrete term violates.

** 3.4 Unification is reversible; computation built around it may not be
The relation-oriented temptation is to say “everything runs backwards.” Resist it. Unification itself does not privilege a left-hand assignment direction, but predicates can have operational requirements, arithmetic can require instantiated inputs, search can diverge, and side effects are not relational.

So we adopt a stricter rule throughout the book: for every important predicate, document and test the useful calling patterns. A relation's declarative reading and its practically terminating modes are both part of engineering it.

** 3.5 Implementation boundary -- occurs check and cyclic terms
For ordinary finite data, the mental model above is enough to learn useful Prolog. There is, however, a famous edge case you should see early so the simplified story never becomes a false claim.

Consider:

#+begin_src prolog
X = node(X).
#+end_src

Mathematically, finite first-order unification would reject binding a variable to a term that contains that same variable. SWI-SPECIFIC: ordinary SWI-Prolog unification permits cyclic (rational) terms by default. The manual documents =unify_with_occurs_check/2= for sound unification and an =occurs_check= flag that can alter ordinary/head unification behavior [cite:@swi-unification].

Therefore this project includes the regression:

#+begin_src prolog
unify_with_occurs_check(X, node(X)).
#+end_src

which is expected to fail.

Do not set a global flag merely to make the chapter's simplified examples “look right.” Instead, understand the boundary: our beginner project uses finite acyclic data; SWI has a broader term model; when acyclicity is a correctness requirement, make it explicit and test it.

** 3.6 Debugging unification failures
When two terms fail to unify, inspect in this order:

1. Do their functors and arities agree?
2. Are you confusing an atom with a variable because of capitalization?
3. Are you confusing an atom with a SWI string?
4. Does a repeated variable impose an equality you did not intend?
5. Did an earlier goal bind the variable more specifically than you remembered?
6. Are you at a cyclic-term/occurs-check boundary?

This checklist is deliberately structural. “Prolog backtracked” is not an explanation of a unification failure.

** 3.7 Exercises
1. Compute the most general bindings, or explain failure, for five pairs of finite terms of your own design.
2. Write two queries over Project 1 whose only difference is whether a variable is shared across goals. Predict both answer sets.
3. Create one test that protects the direction =mentor(Mentor, Student)=.
4. Explain why repeated =_= occurrences do not create an equality constraint, then rewrite the query using a named variable so they do.
5. Run both =X = node(X)= and =unify_with_occurs_check(X, node(X))=. Record the exact SWI-Prolog version and observed result. Label the first behavior SWI-specific in your notes.

* Project 1 -- Relational Query System, Milestone 1
:PROPERTIES:
:ID:       6adaeccb-d0ea-4563-8634-a33e6f34c3dd
:END:

The first deliverable is intentionally small but real. =books/prolog/code/relational-query/community.pl= contains synthetic facts and three derived relations. =test_community.pl= contains PL-Unit regressions. PL-Unit is SWI-Prolog's unit-testing library [cite:@swi-plunit].

Run the suite from the repository root:

#+begin_src sh
bash books/prolog/code/run-tests
#+end_src

The milestone is complete only when the tests actually execute under SWI-Prolog. Reading the source and deciding that it “looks right” is not verification.

** Required behaviors
- known people can be queried;
- unknown people fail cleanly;
- mentor direction is explicit and tested;
- a person cannot be their own =same_neighborhood/2= answer;
- project peers enumerate the expected project relation;
- a shared variable across two goals acts as a relational join;
- sound unification rejects construction of a new cycle.

** Extension challenge
Add a new person who lives in Harbor, works on Beacon, and is mentored by Noor. Before running anything, list exactly which existing query answer sets should change and which must remain unchanged. Then update the tests first and the facts second.

This “predict the blast radius” exercise will recur. A logic program can be tiny while its consequence set is not. Learning to reason about that consequence set is the beginning of being capable with Prolog rather than merely familiar with its syntax.

* What comes next
The next foundation slice keeps this same application and adds recursion and lists instead of resetting to a new toy. We will derive multi-hop relations, inspect termination and solution multiplicity, then introduce list relations where they solve an actual project need. Backtracking becomes visible as an execution mechanism only after you already have relations worth searching.
