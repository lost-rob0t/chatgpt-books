#+title: Prolog + LLMs: Neuro-Symbolic Systems from First Principles
:PROPERTIES:
:ID:       a9ba742b-d4e2-511e-9fef-c28ad5137bcc
:END:
#+bibliography: ../references.bib

* Reader contract
This book is standalone. It teaches enough Prolog to build, inspect, test, and debug the symbolic side of every later integration rather than asking the reader to treat Prolog as an opaque verifier. The sibling volume /Prolog for Beginners: Thinking in Relations/ remains the deeper pure-Prolog course; this volume does not require it.

The second contract is stricter: language-model output is untrusted external input. A model may eventually propose terms, facts, queries, plans, or explanations only through an explicit interface that can reject malformed, unsupported, contradictory, stale, or over-budget work. Fluency is not evidence. Text that merely looks like Prolog is still text.

The third contract is empirical. Version-sensitive claims about SWI-Prolog, model providers, structured generation, tool calling, or named neuro-symbolic systems require current primary-source research. Model quality, latency, cost, and benchmark claims require recorded runs. The opening project therefore begins with no model at all: first we build a deterministic relation we can test.

On 2026-09-16 the official SWI stable channel contains the 10.0.2 manual and release artifacts [cite:@swi-stable-download]. CI records the actual interpreter version used for each tested project slice instead of pretending the documentation version and test runner are necessarily identical.

* Part I -- Learn enough Prolog to distrust magic

** Chapter 1 -- Relations before prompts
:PROPERTIES:
:ID:       2f44a05d-e760-4bf0-94e6-f73a2fd2867e
:END:

*** 1.1 Start with a question the system can answer
Before an LLM can contribute anything safely, the symbolic side needs a crisp job. Project 1 is a small task-dependency system. It knows synthetic tasks, owners, statuses, tags, and dependency edges. Later chapters will add parsing, constraints, explanation, and finally an external model boundary. For now it is deliberately boring: ordinary Prolog clauses and tests.

The canonical source is =books/prolog-llms/code/relational-task-solver/task_solver.pl=. A simplified relation looks like this:

#+begin_src prolog
task(collect_sources, ada, ready, [research, prolog]).
task(normalize_terms, ben, ready, [prolog, validation]).
depends_on(normalize_terms, collect_sources).
#+end_src

Read =task/4= as a four-place relation. The slash notation is a predicate indicator: predicate name plus arity. It does not mean division. The first fact states one relationship among four terms. Nothing here says that a task is a mutable object with fields, or that =ada= is a variable containing a string. Those interpretations come from other programming styles, not from these clauses.

Ask a complete question, then ask for bindings:

#+begin_src prolog
?- task(collect_sources, ada, ready, [research, prolog]).
?- task(collect_sources, Owner, Status, Tags).
#+end_src

A variable starts with an uppercase letter or underscore under the default syntax used in this book. SWI-Prolog's syntax is close to traditional/ISO Prolog but includes extensions; the manual documents the precise lexical rules and optional modes [cite:@swi-syntax]. The important idea is not capitalization trivia. A variable marks a place where a query can discover a term.

*** 1.2 A query is not a prompt
A prompt asks a model to produce a continuation according to learned behavior. A Prolog query asks whether a goal succeeds through the program's proof search, possibly producing substitutions for variables. These are different interfaces with different failure modes.

#+begin_src prolog
?- task(Task, ada, Status, Tags).
#+end_src

can enumerate tasks owned by Ada. If the knowledge base contains no task owned by =mara=, the corresponding query can simply fail. Failure does not mean a parser crashed, a network timed out, or reality proved the opposite. It means this goal did not succeed under the current program and data.

Keep three outcomes separate from day one:
- *success*: at least one proof/substitution satisfies the goal;
- *logical failure*: search finds no proof for the goal under the program;
- *error/exception*: the program cannot perform the requested operation normally.

Later, the typed LLM gateway will add schema rejection, unknown relation, timeout, stale result, and provider failure. It must not erase the distinctions Prolog already gives us.

*** 1.3 Shared variables are joins
Suppose we want Ada's tasks that also have the tag =prolog=:

#+begin_src prolog
?- task(Task, ada, _Status, _Tags),
   has_tag(Task, prolog).
#+end_src

The same variable =Task= appears in both goals. That is the join. Prolog cannot choose one task for the first occurrence and an unrelated task for the second while still calling them the same variable.

This becomes a central neuro-symbolic habit: represent agreement as shared structure, not as prose such as “please make sure this is the same task.” A future model can propose a candidate identifier, but the symbolic program can still require the identifier to unify with the relation it is checking.

*** 1.4 Direction and argument roles are part of the model
Project 1 records:

#+begin_src prolog
depends_on(normalize_terms, collect_sources).
#+end_src

The intended reading is =depends_on(Task, Dependency)=. Reversing the arguments asks a different question. The test suite includes a regression requiring the reversed fact to fail.

This gets more important once natural language enters the system. “Normalization follows collection” is linguistically flexible; a predicate is not. The integration layer must normalize candidate text into a fixed relation schema with explicit argument roles before Prolog treats it as candidate data.

*** 1.5 Preserve evidence before generating explanations
Project 1 stores provenance beside its synthetic fixture records. The public =task/4= relation stays pleasant to query while =explain_task/2= returns structured evidence:

#+begin_src prolog
explanation(
  task(normalize_terms),
  supports([
    fact(task(normalize_terms, ben, ready, [prolog, validation]),
         source(book_fixture, task_normalize_terms))
  ])).
#+end_src

The explanation is a term, not a generated paragraph. Later a model may summarize it, but the evidence identity must survive independently of the prose.

#+caption: Project 1 keeps deterministic symbolic evidence and explanation ahead of the later model boundary.
#+attr_html: :alt Synthetic task facts and query terms feed unification, optional dependency traversal, and structured explanation; the later typed model gateway enters only through validation gates.
[[file:assets/project1-foundation-flow.svg]]

*** 1.6 Failure lab -- break the relation, not the prompt
Make a temporary copy of the project source and introduce one defect at a time: write =Ada= where you intended =ada=; reverse one =depends_on/2= edge; change a call from =task/4= to =task/3=; misspell a predicate; remove a clause-ending full stop. Before running each copy, predict syntax error, arity/existence error, clean logical failure, or surprising success. “Prolog is weird” is not a diagnosis.

** Chapter 2 -- Unification is the first verifier
:PROPERTIES:
:ID:       88f7183f-8f39-4700-8c43-98f8553bea80
:END:

*** 2.1 Terms have shape
Prolog's core data model is small enough to inspect directly:

#+begin_src prolog
collect_sources
42
Task
task(normalize_terms, ben, ready, [prolog, validation])
source(book_fixture, task_normalize_terms)
explanation(task(normalize_terms), supports([]))
#+end_src

For the opening chapters, classify these as variables, atoms, numbers, lists, and compound terms. A compound term has a functor and arguments. A term that resembles code is still data until some explicitly invoked predicate interprets it.

That last sentence is a boundary we will reuse. The future gateway may accept a closed term such as =candidate_task(normalize_terms)= after parsing and validation. It does not gain the right to send arbitrary source text and have the runtime “figure out” whether to call it.

*** 2.2 Unification makes two terms agree
SWI-Prolog documents =/2= as unification and uses unification throughout clause matching [cite:@swi-unification]. Consider:

#+begin_example
Task = normalize_terms
pair(Task, Owner) = pair(normalize_terms, ben)
task(Id, Owner, ready, Tags) = task(check_constraints, ada, ready, [prolog])
#+end_example

Now compare failures:

#+begin_example
normalize_terms = collect_sources
pair(X, X) = pair(ada, ben)
task(a, b) = task(a, b, c)
source(book_fixture, X) = evidence(api, X)
#+end_example

A repeated variable is a constraint. =pair(X,X)= cannot become =pair(ada,ben)= because one logical variable cannot simultaneously denote two different atoms in the same branch.

*** 2.3 Structural validation is not truth
If a future LLM proposes a candidate term, unification can help us test closed structure: expected functor, arity, repeated-variable relationships, and allowed term shapes. Successful unification does not prove the candidate describes reality or is supported by evidence.

The later architecture therefore separates four questions:
1. Can the external response be parsed as data?
2. Does the data fit the closed schema?
3. Is the proposed fact supported by admissible evidence or constraints?
4. What does the symbolic knowledge base entail under its actual rules?

Collapsing those stages into “the model returned valid Prolog” is exactly what this book refuses to do.

*** 2.4 The occurs-check boundary matters
The textbook unification story usually assumes finite trees. SWI-Prolog in its default configuration permits rational/cyclic terms through ordinary unification, while =unify_with_occurs_check/2= prevents creating the self-reference [cite:@swi-unification]. Compare:

#+begin_src prolog
?- X = wrapper(X).
?- unify_with_occurs_check(X, wrapper(X)).
#+end_src

The Project 1 suite tests this boundary explicitly. The first behavior is SWI/runtime-specific and is not presented as a universal promise of “Prolog.” The second is the explicit finite-term boundary used by examples that require one.

Why care in an LLM book? An external producer can hand us deeply nested or pathological structures. Later parsers and validators need size/depth/shape limits in addition to syntactic acceptance. “It parsed as a Prolog term” is not a resource-safety proof.

*** 2.5 Failure lab -- a schema that is almost right
Predict why each succeeds or fails:

#+begin_src prolog
?- task(Id, Owner, ready, Tags) =
   task(normalize_terms, ben, ready, [prolog, validation]).
?- task(Id, Owner, ready, Tags) =
   task(normalize_terms, ben, [prolog, validation]).
?- pair(X, X) = pair(prolog, validation).
#+end_src

Name the exact constraint: functor, arity, concrete value, or repeated-variable consistency. This is the beginning of a validator mindset.

** Chapter 3 -- Recursion, lists, and stopping
:PROPERTIES:
:ID:       f2436342-f838-418a-8c18-13e7a37d08cc
:END:

*** 3.1 Lists are recursive structure
Project 1 stores task tags as lists and intentionally implements a tiny membership relation instead of hiding the mechanism immediately behind a library call:

#+begin_src prolog
list_contains(Item, [Item|_]).
list_contains(Item, [_|Rest]) :-
    list_contains(Item, Rest).
#+end_src

The first clause is a base case. The second strips one head and recurses on the tail. Each recursive step is structurally smaller, which gives an obvious termination argument for a finite proper list.

If =llm= is not present, repeated decomposition eventually reaches the empty list and no clause matches. That is ordinary logical failure, not an exception.

*** 3.2 Recursive graph search needs a stopping story
Task dependencies form a graph. A transitive query is more useful than a direct edge: does =publish_report= depend, directly or indirectly, on =collect_sources=? Project 1's =dependency_path/3= returns an explicit path:

#+begin_example
publish_report
  -> write_explanation
  -> check_constraints
  -> normalize_terms
  -> collect_sources
#+end_example

The implementation carries nodes already seen on the current search branch and refuses to revisit one. Without that state, a dependency cycle can make naive depth-first recursion revisit the same states indefinitely.

*** 3.3 Declarative sense does not guarantee termination
A tempting relation is:

#+begin_src prolog
naive_depends_on(A, B) :- depends_on(A, B).
naive_depends_on(A, B) :-
    depends_on(A, Mid),
    naive_depends_on(Mid, B).
#+end_src

On an acyclic fixture it may appear correct. Add a two-node cycle and ask for a target outside it, and depth-first search can loop. The logical idea “reachability is the transitive closure of edges” can be sensible while the executable search strategy still lacks a termination story.

This prepares us for later agentic systems. A recursion budget is not a production garnish. Any model-driven loop that can revisit states needs stopping rules, duplicate-state handling, or both.

*** 3.4 Explanations preserve the path
=explain_dependency/3= returns the path and the source identity supporting every edge:

#+begin_src prolog
explanation(
  dependency(check_constraints, collect_sources),
  path([check_constraints, normalize_terms, collect_sources]),
  supports([
    fact(depends_on(check_constraints, normalize_terms),
         source(book_fixture, dep_constraints_normalize)),
    fact(depends_on(normalize_terms, collect_sources),
         source(book_fixture, dep_normalize_collect))
  ])).
#+end_src

Later an LLM may turn that structure into readable prose. If its prose invents an unsupported edge, the symbolic trace remains available for checking. Explanation is strongest when it is downstream of evidence, not a fluent replacement for evidence.

*** 3.5 Tests are executable claims
SWI-Prolog's =library(plunit)= provides named test units and =run_tests= entry points [cite:@swi-plunit]. Project 1 uses a dedicated runner that first checks that the named test unit actually loaded, then runs it. A missing suite must not look green merely because the interpreter exited successfully.

The opening suite checks relation direction, shared-variable joins, list-tag queries, direct/transitive paths, missing-path failure, provenance-bearing explanations, sound occurs-check unification, the current SWI cyclic-term boundary, and bounded termination for an unreachable query in the presence of a two-node dependency cycle. That last regression matters because “we carry a visited set” is only an implementation story until a cyclic fixture actually tries to break it. Tests assert results; merely calling a predicate is not protection.

*** 3.6 Failure lab -- three recursion bugs
Use temporary experimental copies, not canonical project code. Remove the base case from =list_contains/2=. Then change the recursive call to recurse on the original list instead of =Rest=. Finally replace =dependency_path/3= with the naive relation above, add a two-node cycle, and run the experiment under an explicit time limit. Explain each failure in terms of structural progress and visited state.

*** 3.7 What Project 1 can honestly claim now
At this milestone the project is a deterministic symbolic baseline. It represents synthetic tasks, answers relational queries, follows finite dependency paths with branch-local cycle avoidance, and returns structured provenance-bearing explanations. Its suite is designed to exercise those claims on SWI-Prolog.

It cannot yet parse the planned DCG mini-language, solve the CLP(FD) scheduling subproblem, expose the typed LLM gateway, retrieve evidence, or perform recursive language-model execution. Those are dependency-ordered future milestones, not features implied by the book title.

** Chapter 4 -- Backtracking and explicit control
:PROPERTIES:
:ID:       9767e80f-a9cc-4802-b1c2-3b98bbb14922
:END:

*** 4.1 One success can hide more answers
Until now many examples have asked whether a goal succeeds or have collected all answers with =findall/3=. That can hide the mechanism between those two views. A Prolog goal may succeed while leaving a *choice point*: a place the engine can revisit if the caller requests another answer or a later goal fails.

Project 1 milestone B makes that visible with a relation whose multiplicity is intentional:

#+begin_src prolog
ready_task(Task, Owner) :-
    task(Task, Owner, ready, _).
#+end_src

On the current synthetic fixture there are three ready tasks. Querying =ready_task(Task, Owner)= can therefore produce three substitutions. That is not accidental nondeterminism. The relation means “Task owned by Owner is ready,” and more than one pair satisfies it.

A useful mental model is a stack of unfinished alternatives. The first proof gives one answer. Asking for another answer causes the engine to *backtrack* to the most recent relevant choice point, undo bindings made after that point, and try the next alternative. The declarative relation did not change; the operational search moved to another proof.

SWI-Prolog documents conjunction, disjunction, cut, if-then-else, and related constructs as control predicates governing this search [cite:@swi-control].

*** 4.2 Goal order is executable even when conjunction is logical
Compare these two queries:

#+begin_src prolog
?- task(Task, Owner, ready, _), has_tag(Task, prolog).
?- has_tag(Task, prolog), task(Task, Owner, ready, _).
#+end_src

For the finite fixture both can describe the same successful Task/Owner pairs. They do not necessarily explore them in the same way. The first query enumerates ready tasks and then checks each tag. The second enumerates tasks with the tag and then checks readiness.

This distinction matters later when one goal is expensive, nonterminating, impure, or an external call. Logical conjunction is not permission to pretend runtime order does not exist. In a neuro-symbolic system the safe design is usually to put cheap deterministic validation before expensive external work and to make any side-effecting boundary explicit.

Exercise: draw a tiny search tree for the current fixture. Mark each =task/4= alternative, show which branch =has_tag(Task, prolog)= accepts, and identify where a redo would occur.

*** 4.3 once/1 changes the contract
Sometimes a caller genuinely wants no more than one solution. Project 1 exposes that decision under a different predicate name:

#+begin_src prolog
first_ready_task(Task, Owner) :-
    once(ready_task(Task, Owner)).
#+end_src

SWI-Prolog documents =once/1= as a first-success commitment [cite:@swi-control]. The important part is not the spelling; it is that the public contract changed. =ready_task/2= means “enumerate ready tasks.” =first_ready_task/2= means “return at most the first answer in current search order.”

That first answer is *not* the highest priority task. No priority relation exists in the project. If we later need priority, we must model priority and test it. Treating program order as business meaning is exactly the sort of invisible assumption that becomes dangerous when a model proposes candidates.

This gives us a future integration rule: when a verifier finds several admissible interpretations, silently wrapping the query in =once/1= does not resolve ambiguity. It only hides alternatives. The gateway must have an explicit policy for multiple candidates.

*** 4.4 Cut is understandable only after the alternatives are visible
The cut =!/0= prunes choice points within its documented scope [cite:@swi-control]. A tiny definition such as

#+begin_src prolog
first_ready_with_cut(Task, Owner) :-
    ready_task(Task, Owner),
    !.
#+end_src

can imitate the first-answer behavior of the previous example. We do *not* add this predicate to the canonical project API, because =once/1= says the intended boundary more directly.

Cut is not a truth operator. It does not prove the chosen answer is better, more certain, or unique. It changes search. Before adding a cut, name the alternatives it will discard and explain why discarding them belongs to the predicate's contract.

Failure lab: copy =ready_task/2= to a scratch file, add a cut after its first successful =task/4= call, then ask for all answers. Explain the missing tasks in terms of a pruned choice point rather than saying “cut makes it deterministic.” That description is incomplete unless you say *which answers were removed*.

*** 4.5 If-then-else can make a relational-looking predicate mode-sensitive
Consider this tempting classifier:

#+begin_src prolog
task_decision(Task, Decision) :-
    (   task(Task, _, blocked, _)
    ->  Decision = investigate
    ;   task(Task, _, ready, _)
    ->  Decision = execute
    ;   Decision = wait
    ).
#+end_src

For a ground =Task= this may be a reasonable control flow. With =Task= unbound, however, the first condition can find a blocked task and commit inside the if-then-else condition, so the predicate is not a general enumerator of every task and decision. Current SWI documentation makes that commitment behavior explicit [cite:@swi-control].

This is why “it is written in Prolog” is not the same as “it is relational in every mode.” The later typed gateway will not be allowed to invent a goal and assume every argument pattern is supported. Query shape is part of the interface.

*** 4.6 Finite failure is not world knowledge
SWI-Prolog's =\+/1= succeeds when its goal cannot be proven by finite failure under the current program [cite:@swi-control]. For internal closed fixture checks, that can be useful control. It does not justify a sentence like “the event did not happen in reality” merely because a knowledge base lacks a proof.

That distinction becomes critical in retrieval-backed systems. “No accepted evidence proves X” is a useful verifier result. “X is false in the world” is a stronger epistemic claim and needs a representation that warrants it.

*** 4.7 Tests should expose multiplicity, not hush it
Milestone B changes the suite from treating every leftover choice point as suspicious to classifying multiplicity deliberately. PL-Unit supports multi-answer assertions such as =all(...)= and =set(...)= in addition to =nondet= [cite:@swi-plunit-source]. The project uses =all(...)= for =ready_task/2= because the exact answers are the contract:

#+begin_src prolog
test(ready_tasks_expose_all_choice_point_answers,
     all(Task-Owner == [collect_sources-ada,
                        normalize_terms-ben,
                        write_explanation-lina])) :-
    ready_task(Task, Owner).
#+end_src

By contrast, =first_ready_task/2= is tested as an ordinary deterministic goal. If a test merely adds =nondet= to make a warning disappear, it may be documenting less than the reader thinks.

*** 4.8 Exercises
1. Predict the three =ready_task/2= answers before running them. Then request them one at a time at the top level and mark each redo.
2. Reverse the order of the two goals in the tag/readiness query. Does the answer set change? Does the search order change?
3. Write a scratch predicate that uses =once/1= around =dependency_path/3=. Explain precisely what information it discards if the graph later gains two valid paths.
4. Repair =task_decision/2= so its supported modes are explicit. One acceptable answer is to require a ground task identifier at the interface; another is to redesign the relation. Explain the tradeoff instead of chasing syntactic cleverness.
5. Give one example where =\+ Goal= means “not provable here” but definitely should not be rendered to a user as “false in reality.”

** Chapter 5 -- Modules, tests, and debugging
:PROPERTIES:
:ID:       8d569e90-061d-4c7a-b897-14da653f9aea
:END:

*** 5.1 A module is an interface you can inspect
Project 1 has been a module from the beginning:

#+begin_src prolog
:- module(relational_task_solver,
          [ task/4,
            ready_task/2,
            first_ready_task/2,
            dependency_path/3,
            explain_task/2,
            explain_dependency/3
          ]).
#+end_src

The real export list also includes the other public relations used by earlier chapters. SWI-Prolog's module system gives each module a predicate namespace and uses =module/2= to declare a public interface; =use_module/[1,2]= loads module files and imports exports [cite:@swi-modules;@swi-module-import].

This matters because a symbolic subsystem should have a smaller public surface than “every predicate currently present in the source file.” The export list becomes something a reviewer can inspect and tests can exercise.

*** 5.2 Compose public relations in a second module
Milestone B adds =task_report.pl=:

#+begin_src prolog
:- module(task_report,
          [ ready_report/3
          ]).

:- use_module(task_solver,
              [ ready_task/2,
                explain_task/2
              ]).

ready_report(Task, Owner, Explanation) :-
    ready_task(Task, Owner),
    explain_task(Task, Explanation).
#+end_src

The import list is intentionally explicit. =task_report= does not need to know how task records are stored or how provenance records are represented internally. It asks two public relations to agree on the same =Task= variable.

Notice that the module boundary did not destroy relational behavior. =ready_report/3= can still enumerate ready tasks because =ready_task/2= can. Composition preserves multiplicity unless some later control deliberately commits it.

*** 5.3 Modules are not an authorization system
Do not confuse “not exported” with “safe against hostile input.” SWI's module system is primarily a namespace and program-organization mechanism. The later LLM gateway still needs a closed schema, allowlisted operations, argument validation, budgets, and explicit execution permission.

A model-produced string such as ="relational_task_solver:some_private_goal(X)"= remains untrusted text. We will not parse arbitrary predicate names from it and call them. The fact that Project 1 now has modules makes the safe gateway easier to structure; it does not make arbitrary meta-calling safe.

*** 5.4 A strong test states what kind of relation it expects
PL-Unit provides several ways to express expected behavior [cite:@swi-plunit;@swi-plunit-source]. Use them to make semantics visible:
- ordinary test body :: expect success and, by default, no unintended leftover choice point;
- =[fail]= :: the goal should fail;
- =throws(...)= :: an exception is the expected result;
- =all(...)= :: collect every answer in order and compare the bindings;
- =set(...)= :: compare the answer set when order should not matter;
- =nondet= :: leaving alternatives is acceptable when the alternatives themselves are not the assertion.

Project 1's milestone B test for =ready_task/2= uses =all(...)= because all ready tasks matter. The =first_ready_task/2= test is ordinary/deterministic because committing to one current answer is exactly what that predicate promises. A third regression loads =task_report= and checks that the consumer module produces a provenance-bearing report through the exported API.

This is more than test syntax. Later, when model output crosses a typed boundary, we need tests that distinguish “one acceptable candidate exists” from “these are all accepted candidates” and from “the verifier rejected this candidate.”

*** 5.5 Read a trace as a search story
SWI-Prolog's debugger is based on trace ports. The minimal vocabulary for this chapter is [cite:@swi-debugger]:
- *call* :: a predicate is being invoked;
- *exit* :: that invocation succeeded;
- *redo* :: backtracking asks the invocation for another solution;
- *fail* :: that invocation cannot produce a solution on the current search path.

Run this interactively in a disposable session:

#+begin_src prolog
?- [books/prolog-llms/code/relational-task-solver/task_solver].
?- trace.
?- ready_task(Task, Owner).
#+end_src

Request another solution at the top level and watch for the redo path. Then leave trace mode with =notrace=. Do not copy a transcript from this book and pretend it came from your runtime; the useful exercise is mapping the actual ports you see to the choices in the current source.

Next trace a failing conjunction:

#+begin_src prolog
?- trace.
?- ready_task(Task, Owner), has_tag(Task, missing_tag).
#+end_src

The interesting event is not merely the final =false=. Watch the tag check fail, then the engine redo the earlier ready-task relation and try the next candidate. That is Chapter 4's search tree made observable.

*** 5.6 Debug mode is not a performance benchmark
Current SWI debugger documentation notes that debug mode changes optimization behavior, including disabling last-call optimization and retaining choice-point information needed for debugging [cite:@swi-debugger]. Therefore a trace is evidence about control flow, not a timing or memory benchmark.

If a later performance chapter asks whether one goal order is faster, measure outside trace/debug mode with an explicit benchmark design. “It looked like fewer lines in the tracer” is not a benchmark.

*** 5.7 Debug the boundary, not just the clause
Use this checklist when a future neuro-symbolic request fails:
1. *Parse boundary* -- did external bytes become an allowed data structure?
2. *Schema boundary* -- are functor/fields/argument roles valid?
3. *Module/API boundary* -- which public predicate is actually being invoked?
4. *Search boundary* -- is the predicate deterministic, multi-answer, failing, or diverging for this mode?
5. *Evidence boundary* -- what provenance supports the accepted facts?
6. *External boundary* -- only later, did a provider timeout, stream truncate, or return malformed data?

At Project 1 milestone B only items 3--5 are executable book code. The parser/model/provider layers are still future work. Keeping the list now prevents “the AI failed” from becoming one undifferentiated diagnosis later.

*** 5.8 Failure lab -- make a weak test look green
In a scratch copy, replace the =all(...)= ready-task test with a body that merely calls =ready_task(_, _)= and mark it =nondet=. The test can now pass without asserting which tasks are ready. Delete one ready fixture and observe that the weaker test may still pass.

Restore the =all(...)= assertion. The lesson is not that =nondet= is bad; it is that test options describe contracts. Use the strongest contract the behavior actually promises.

Then break the import list in =task_report.pl= by removing =explain_task/2=. Predict whether loading or calling the module fails, run the test suite, and diagnose the error as an interface/import defect rather than a logical failure in =ready_task/2=.

*** 5.9 What Project 1 can honestly claim after milestone B
After the milestone B suite passes, Project 1 can claim a tested distinction between multi-answer relational enumeration and an explicit first-answer commitment, plus tested composition across an explicit module import boundary. The earlier recursion, cycle-safety, occurs-check, and provenance claims remain covered by the retained regressions.

The interactive tracer behavior in this chapter is DOCUMENTED from current SWI-Prolog sources but is not promoted to TESTED by the CI suite merely because readers are instructed to run it. Likewise, modules are not claimed as a security boundary.

Project 1 still cannot parse the planned mini-language, solve its CLP(FD) scheduling subproblem, expose a typed model gateway, retrieve evidence, or run an RLM-style loop. The next foundation slice is DCGs + constraints + carefully bounded meta-programming.

* Bridge -- why the LLM still stays outside
The current =lost-rob0t/prolog-rlm= source is a useful later case study because its public architecture explicitly separates model strategy from Prolog-owned execution semantics and validates a closed plan language before execution. At the inspected source snapshot the repository exposes parsing/normalization, =plan_validate/4=, and =plan_execute/4= around that boundary [cite:@prolog-rlm-source]. This book has inspected that source snapshot; it has not imported or executed the runtime as part of Project 1.

The original Recursive Language Models work frames long context as an external environment that a model can programmatically inspect and recursively query [cite:@zhang-rlm]. We will study that architecture much later. Its reported benchmark and cost findings remain upstream evidence until this book reproduces an experiment.

The next foundation slice adds a DCG mini-language, a genuine CLP(FD) subproblem, and bounded meta-programming. Only after those mechanisms are executable will the book put a typed wall around a model.
