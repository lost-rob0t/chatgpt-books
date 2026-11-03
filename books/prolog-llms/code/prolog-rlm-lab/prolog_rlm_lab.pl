:- module(prolog_rlm_lab,
          [ validate_plan/2,
            static_budget_check/3,
            budget/3,
            authorize/3
          ]).

/** <module> Prolog-RLM capstone boundary lab

Book-owned teaching model for Chapters 29--31.  It encodes three invariants
documented for the =lost-rob0t/prolog-rlm= typed plan runtime as small,
deterministic SWI-Prolog checks over lab-owned plan data:

  1. Plans are closed data.  validate_plan/2 admits only a fixed vocabulary of
     operation terms, argument shapes, and expression forms.  A term outside
     the closed set is rejected as data; it is never interpreted as a goal.
  2. Static cost is checked before dynamic cost is spent.  validate_plan/2
     computes a structural estimate, static_budget_check/3 compares it with
     the declared budget before execution, and budget/3 charges one shared,
     decreasing balance without partial charges.  Entering a nested plan
     spends the same balance; returning restores only the depth slot.
  3. Authority is separate from availability.  authorize/3 grants an operation
     only when its capability is listed.  It deliberately takes no tool
     registry argument, so an installed closure cannot rescue an ungranted
     operation.

This module is NOT the upstream runtime and does not execute plans.  It is a
teaching simplification whose documented omissions are listed in README.org
next to this file; upstream fidelity is DOCUMENTED-only.
*/

% ----------------------------------------------------------------------
% The closed plan language (Chapter 29)
% ----------------------------------------------------------------------

% The executable operation vocabulary.  Anything else is inert data.
plan_op(context(_, _, _)).
plan_op(model(_, _, _, _)).
plan_op(rlm(_, _)).
plan_op(tool(_, _, _)).
plan_op(parallel(_, _)).
plan_op(retry(_, _, _)).
plan_op(checkpoint(_)).
plan_op(final(_)).

% Closed expression grammar used by the lab: input selection, references to
% already-bound plan variables, and literal atoms, numbers, strings, lists.
fully_closed_expr(Expr, _) :- atom(Expr).
fully_closed_expr(Expr, _) :- number(Expr).
fully_closed_expr(Expr, _) :- string(Expr).
fully_closed_expr(input, _).
fully_closed_expr(input(Field), _) :- atom(Field).
fully_closed_expr(var(Name), Bindings) :- atom(Name), memberchk(Name, Bindings).
fully_closed_expr([H|T], B) :- fully_closed_expr(H, B), fully_closed_expr(T, B).

% unbound_var(+Expr, +Bindings, -Name): the first var(Name) whose Name is
% absent from Bindings.  This is a data walk over terms; it never calls the
% expression.
unbound_var(var(Name), Bindings, Name) :-
    \+ memberchk(Name, Bindings).
unbound_var([H|T], Bindings, Name) :-
    (   unbound_var(H, Bindings, Name)
    ->  true
    ;   unbound_var(T, Bindings, Name)
    ).
unbound_var(Expr, Bindings, Name) :-
    compound(Expr),
    Expr \= var(_),
    Expr \= [_|_],
    arg(_, Expr, Sub),
    unbound_var(Sub, Bindings, Name).

% expr_gate(+Expr, +Bindings, +Op, -Gate): ok, or the reason the expression is
% not part of the closed grammar.
expr_gate(Expr, Bindings, _Op, ok) :-
    fully_closed_expr(Expr, Bindings),
    !.
expr_gate(Expr, Bindings, _Op, error(unbound_variable(Name))) :-
    unbound_var(Expr, Bindings, Name),
    !.
expr_gate(_Expr, _Bindings, Op, error(malformed_operation(Op))).

% gate_outcome(+Gate, +Bind, +B0, -B1, -Status): binding ops only bind after
% their own expressions were admitted, and a binding name may be used once.
gate_outcome(ok, Bind, B0, [Bind|B0], ok) :-
    \+ memberchk(Bind, B0),
    !.
gate_outcome(ok, Bind, B0, B0, error(duplicate_binding(Bind))).
gate_outcome(error(Reason), _Bind, B0, B0, error(Reason)).

% ----------------------------------------------------------------------
% validate_plan/2
% ----------------------------------------------------------------------

validate_plan(Plan, Status) :-
    (   Plan = plan(Ops),
        is_list(Ops)
    ->  walk_ops(Ops, no_final, [], est(0,0,0,0), WalkStatus),
        (   WalkStatus = ok(_Bindings, est(S,D,T,M))
        ->  Status = ok(estimate(S, D, T, M))
        ;   WalkStatus = error(Reason)
        ->  Status = error(Reason)
        )
    ;   Status = error(malformed_plan(Plan))
    ).

% walk_ops(+Ops, +FinalSeen, +Bindings, +Est0, -Status)
% Status = ok(Bindings, Est) | error(Reason).  Est accumulates the structural
% estimate of Chapter 30: steps, maximum depth, tool calls, model calls.
% A plan must contain exactly one final/1 and it must be last.
walk_ops([], FinalSeen, Bindings, Est, Status) :-
    (   FinalSeen == final_seen
    ->  Status = ok(Bindings, Est)
    ;   Status = error(bad_final(no_final))
    ).
walk_ops([Op|Rest], FinalSeen0, Bindings0, est(S0,D0,T0,M0), Status) :-
    op_status(Op, FinalSeen0, Rest, Bindings0, Bindings1, Cost, OpStatus),
    Cost = est(SC,DC,TC,MC),
    S1 is S0 + SC,
    D1 is max(D0, DC),
    T1 is T0 + TC,
    M1 is M0 + MC,
    (   OpStatus == ok
    ->  (   Op = final(_)
        ->  FinalSeen1 = final_seen
        ;   FinalSeen1 = FinalSeen0
        ),
        walk_ops(Rest, FinalSeen1, Bindings1, est(S1,D1,T1,M1), Status)
    ;   Status = OpStatus
    ).

% Single-clause dispatcher: one operation shape per branch.  A term outside
% the closed vocabulary -- including callable-looking terms such as
% call(shell(id)) and known names with wrong arity -- lands in the final
% branch as data, never as a goal.
op_status(Op, FinalSeen, Rest, Bindings0, Bindings1, Cost, Status) :-
    (   Op = final(ValueExpr)
    ->  Bindings1 = Bindings0,
        Cost = est(1,1,0,0),
        final_op(ValueExpr, FinalSeen, Rest, Bindings0, Status)
    ;   Op = checkpoint(Label)
    ->  Bindings1 = Bindings0,
        Cost = est(1,1,0,0),
        checkpoint_op(Label, Status)
    ;   Op = context(HandleExpr, Action, Bind)
    ->  Cost = est(1,1,0,0),
        bound_op(Op, HandleExpr, Action, Bind, Bindings0, Bindings1, Status)
    ;   Op = model(ProviderName, PromptExpr, RequestOptions, Bind)
    ->  Cost = est(1,1,0,1),
        model_op(ProviderName, PromptExpr, RequestOptions, Bind, Bindings0, Bindings1, Status)
    ;   Op = tool(ToolName, ArgsExpr, Bind)
    ->  Cost = est(1,1,1,0),
        bound_op(Op, ArgsExpr, ToolName, Bind, Bindings0, Bindings1, Status)
    ;   Op = rlm(SubPlan, Bind)
    ->  nested_op(rlm(SubPlan, Bind), SubPlan, Bind, Bindings0, Bindings1, Cost, Status)
    ;   Op = parallel(SubPlans, Bind)
    ->  parallel_op(SubPlans, Bind, Bindings0, Bindings1, Cost, Status)
    ;   Op = retry(Attempts, SubPlan, Bind)
    ->  retry_op(Attempts, SubPlan, Bind, Bindings0, Bindings1, Cost, Status)
    ;   Bindings1 = Bindings0,
        Cost = est(0,0,0,0),
        Status = error(unknown_operation(Op))
    ).

final_op(ValueExpr, FinalSeen, Rest, B0, Status) :-
    (   FinalSeen == final_seen
    ->  Status = error(bad_final(multiple_final))
    ;   Rest \== []
    ->  Status = error(bad_final(final_not_last))
    ;   expr_gate(ValueExpr, B0, final(ValueExpr), ok)
    ->  Status = ok
    ;   unbound_var(ValueExpr, B0, Name)
    ->  Status = error(unbound_variable(Name))
    ;   Status = error(malformed_operation(final(ValueExpr)))
    ).

checkpoint_op(Label, Status) :-
    (   atom(Label)
    ->  Status = ok
    ;   Status = error(malformed_operation(checkpoint(Label)))
    ).

% Shared shape for context/3 and tool/3: one gated expression plus a fresh
% single-use binding name.
bound_op(Op, Expr, HeadAtom, Bind, B0, B1, Status) :-
    (   atom(HeadAtom),
        atom(Bind),
        expr_gate(Expr, B0, Op, Gate)
    ->  gate_outcome(Gate, Bind, B0, B1, Status)
    ;   B1 = B0,
        Status = error(malformed_operation(Op))
    ).

% The lab admits RequestOptions as inert list data only; it never opens them.
model_op(ProviderName, PromptExpr, RequestOptions, Bind, B0, B1, Status) :-
    Op = model(ProviderName, PromptExpr, RequestOptions, Bind),
    (   atom(ProviderName),
        atom(Bind),
        is_list(RequestOptions),
        expr_gate(PromptExpr, B0, Op, Gate)
    ->  gate_outcome(Gate, Bind, B0, B1, Status)
    ;   B1 = B0,
        Status = error(malformed_operation(Op))
    ).

% Nested plans are validated on their own walk against the parent's bindings.
% On return the child's lexical bindings are discarded; only Bind joins the
% parent scope, mirroring the scope/accounting separation of Chapter 30.
nested_op(Op, SubPlan, Bind, B0, B1, Cost, Status) :-
    (   atom(Bind)
    ->  walk_child(SubPlan, Bind, B0, B1, est(CS,CD,CT,CM), Status),
        rlm_cost(est(CS,CD,CT,CM), Cost)
    ;   B1 = B0, Cost = est(0,0,0,0),
        Status = error(malformed_operation(Op))
    ).

% walk_child(+SubPlan, +Bind, +B0, -B1, -Cost, -Status)
walk_child(SubPlan, Bind, B0, B1, Cost, Status) :-
    (   SubPlan = plan(ChildOps),
        is_list(ChildOps)
    ->  walk_ops(ChildOps, no_final, B0, est(0,0,0,0), WalkStatus),
        child_bind_outcome(WalkStatus, Bind, B0, B1, Cost, Status)
    ;   B1 = B0, Cost = est(0,0,0,0),
        Status = error(malformed_operation(nested_plan(SubPlan)))
    ).

% Chapter 30: a parallel step contributes its children's work, each child
% estimated at one greater depth.
parallel_op(SubPlans, Bind, B0, B1, Cost, Status) :-
    (   is_list(SubPlans),
        SubPlans \== [],
        atom(Bind)
    ->  children_sum(SubPlans, B0, est(CS,CD,CT,CM), ChildStatus),
        child_add_result(ChildStatus, Bind, B0, B1, est(CS,CD,CT,CM), Cost, Status)
    ;   B1 = B0, Cost = est(0,0,0,0),
        Status = error(malformed_operation(parallel(SubPlans, Bind)))
    ).

% Chapter 30: a retry multiplies the estimated child work by the maximum
% number of attempts.
retry_op(Attempts, SubPlan, Bind, B0, B1, Cost, Status) :-
    (   integer(Attempts),
        Attempts >= 1,
        atom(Bind)
    ->  walk_child(SubPlan, Bind, B0, B1, est(CS,CD,CT,CM), Status),
        retry_cost(est(CS,CD,CT,CM), Attempts, Cost)
    ;   B1 = B0, Cost = est(0,0,0,0),
        Status = error(malformed_operation(retry(Attempts, SubPlan, Bind)))
    ).

child_bind_outcome(ok(_ChildBindings, Cost), Bind, B0, [Bind|B0], Cost, ok) :-
    \+ memberchk(Bind, B0),
    !.
child_bind_outcome(ok(_ChildBindings, Cost), Bind, B0, B0, Cost, error(duplicate_binding(Bind))).
child_bind_outcome(error(Reason), _Bind, B0, B0, est(0,0,0,0), error(Reason)).

% children_sum(+SubPlans, +Bindings, -Cost, -Status): summed child work with
% each child estimated at one greater depth; child-local bindings are
% discarded and only Bind joins the parent scope.
children_sum([], _B, est(0,0,0,0), ok) :- !.
children_sum([Sub|Rest], B, est(S,D,T,M), Status) :-
    child_cost(Sub, B, est(SC,DC,TC,MC), SubStatus),
    (   SubStatus == ok
    ->  children_sum(Rest, B, est(SR,DR,TR,MR), Status),
        S is SC + SR,
        D is max(DC, DR),
        T is TC + TR,
        M is MC + MR
    ;   Status = SubStatus
    ).

child_cost(SubPlan, Bindings, Cost, Status) :-
    (   SubPlan = plan(ChildOps),
        is_list(ChildOps)
    ->  walk_ops(ChildOps, no_final, Bindings, est(0,0,0,0), WalkStatus),
        (   WalkStatus = ok(_ChildBindings, Cost)
        ->  Status = ok
        ;   WalkStatus = error(Reason)
        ->  Status = error(Reason)
        )
    ;   Cost = est(0,0,0,0),
        Status = error(malformed_operation(nested_plan(SubPlan)))
    ).

child_add_result(ok, Bind, B0, [Bind|B0], est(CS,CD,CT,CM), est(S1,D1,CT,CM), ok) :-
    \+ memberchk(Bind, B0),
    !,
    S1 is CS + 1,
    D1 is CD + 1.
child_add_result(ok, Bind, B0, B0, est(CS,CD,CT,CM), est(CS,CD,CT,CM),
                 error(duplicate_binding(Bind))).
child_add_result(error(Reason), _Bind, B0, B0, _Est, est(0,0,0,0), error(Reason)).

rlm_cost(est(CS,CD,CT,CM), est(CS1,CD1,CT,CM)) :-
    CS1 is CS + 1,
    CD1 is CD + 1.

retry_cost(est(CS,CD,CT,CM), Attempts, est(CS1,CD1,CT1,CM1)) :-
    CS1 is CS * Attempts,
    CT1 is CT * Attempts,
    CM1 is CM * Attempts,
    CD1 is CD + 1.

% ----------------------------------------------------------------------
% static_budget_check/3: static cost before dynamic cost (Chapter 30)
% ----------------------------------------------------------------------

static_budget_check(Estimate, Budget, Status) :-
    budget_shape(Budget),
    !,
    static_fields([max_steps, max_depth, max_tool_calls, max_model_calls],
                  Estimate, Budget, Status).
static_budget_check(_Estimate, Budget, error(malformed_budget(Budget))).

% Declared-budget fields (the static maxima) are distinct from the dynamic
% balance fields of budget/3.
budget_field(max_steps).
budget_field(max_depth).
budget_field(max_tool_calls).
budget_field(max_model_calls).

budget_shape(Budget) :-
    is_dict(Budget),
    forall(budget_field(Field),
           (   get_dict(Field, Budget, Value),
               integer(Value),
               Value >= 0
           )).

static_fields([], _Estimate, _Budget, ok(ready)).
static_fields([Field|Rest], Estimate, Budget, Status) :-
    estimate_field(Field, Used, Estimate),
    get_dict(Field, Budget, Allowed),
    (   Used =< Allowed
    ->  static_fields(Rest, Estimate, Budget, Status)
    ;   Status = error(budget_exceeded(Field, Used, Allowed))
    ).

estimate_field(max_steps, S, estimate(S,_,_,_)).
estimate_field(max_depth, D, estimate(_,D,_,_)).
estimate_field(max_tool_calls, T, estimate(_,_,T,_)).
estimate_field(max_model_calls, M, estimate(_,_,_,M)).

% ----------------------------------------------------------------------
% budget/3: one decreasing balance (Chapter 30)
% ----------------------------------------------------------------------

% Balance fields are the lab's dynamic counters.  Depth is a decreasing slot:
% enter_rlm spends one, exit_rlm restores exactly one.  Spent steps, tool
% calls, and model calls are never restored by exit_rlm.
balance_field(steps).
balance_field(depth).
balance_field(tool_calls).
balance_field(model_calls).

balance_shape(Balance) :-
    is_dict(Balance),
    forall(balance_field(Field),
           (   get_dict(Field, Balance, Value),
               integer(Value),
               Value >= 0
           )).

budget(Demand, Balance, Status) :-
    valid_demand(Demand),
    !,
    (   balance_shape(Balance)
    ->  apply_demand(Demand, Balance, Status)
    ;   Status = error(malformed_balance(Balance))
    ).
budget(Demand, _Balance, error(invalid_demand(Demand))).

valid_demand(charge(Field, N)) :-
    balance_field(Field),
    integer(N),
    N >= 1.
valid_demand(enter_rlm).
valid_demand(exit_rlm).

apply_demand(charge(Field, N), Balance, Status) :-
    get_dict(Field, Balance, Remaining),
    (   Remaining >= N
    ->  Remaining1 is Remaining - N,
        put_dict(Field, Balance, Remaining1, Balance1),
        Status = ok(Balance1)
    ;   Status = error(budget_exceeded(Field, N, Remaining))
    ).
apply_demand(enter_rlm, Balance, Status) :-
    get_dict(depth, Balance, DepthLeft),
    (   DepthLeft >= 1
    ->  DepthLeft1 is DepthLeft - 1,
        put_dict(depth, Balance, DepthLeft1, Balance1),
        Status = ok(Balance1)
    ;   Status = error(budget_exceeded(depth, 1, DepthLeft))
    ).
apply_demand(exit_rlm, Balance, ok(Balance1)) :-
    get_dict(depth, Balance, DepthLeft),
    DepthLeft1 is DepthLeft + 1,
    put_dict(depth, Balance, DepthLeft1, Balance1).

% ----------------------------------------------------------------------
% authorize/3: capability policy before execution (Chapter 29, boundary 2)
% ----------------------------------------------------------------------

authorize(Op, Capabilities, Status) :-
    (   capability_requirement(Op, Cap)
    ->  (   memberchk(Cap, Capabilities)
        ->  Status = ok(Op)
        ;   Status = error(capability_denied(Cap))
        )
    ;   plan_op(Op)
    ->  Status = ok(Op)
    ;   Status = error(unknown_operation(Op))
    ).

capability_requirement(tool(Name,_,_), tool(Name)).
capability_requirement(model(_,_,_,_), model).
capability_requirement(context(_,_,_), context).
capability_requirement(rlm(_,_), rlm).
capability_requirement(checkpoint(_), checkpoint).
% parallel/2 and retry/3 need no capability of their own; their nested plans
% are validated and authorized on their own walks.
