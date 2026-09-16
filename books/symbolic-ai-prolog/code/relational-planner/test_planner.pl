:- begin_tests(relational_planner).

:- use_module(planner).
:- use_module(field_service_domain).

test(canonical_state_is_ground_sorted_set) :-
    canonical_state([ticket_open(inc7),
                     failed(node7),
                     ticket_open(inc7)],
                    State),
    assertion(State == [failed(node7), ticket_open(inc7)]).

test(nonground_state_is_rejected,
     [error(instantiation_error)]) :-
    canonical_state([known(a), unknown(_)], _).

test(shared_precondition_binding_must_be_consistent) :-
    Schema = schema(travel,
                    travel(Tech, From, To),
                    [tech_at(Tech, From), link(From, To)],
                    [tech_at(Tech, To)],
                    [tech_at(Tech, From)]),
    State = [tech_at(tech1, depot),
             link(depot, site_a),
             link(other, nowhere)],
    findall(Action,
            applicable(Schema,
                       State,
                       instance(travel, Action, _, _)),
            Actions),
    assertion(Actions == [travel(tech1, depot, site_a)]).

test(schema_is_freshened_for_each_applicability_attempt) :-
    Schema = schema(travel,
                    travel(Tech, From, To),
                    [tech_at(Tech, From), link(From, To)],
                    [tech_at(Tech, To)],
                    [tech_at(Tech, From)]),
    once(applicable(Schema,
                    [tech_at(tech1, depot), link(depot, site_a)],
                    instance(travel,
                             travel(tech1, depot, site_a),
                             _,
                             _))),
    assertion(var(Tech)),
    assertion(var(From)),
    assertion(var(To)),
    once(applicable(Schema,
                    [tech_at(tech2, cage), link(cage, bench)],
                    instance(travel,
                             travel(tech2, cage, bench),
                             _,
                             _))).

test(effect_application_preserves_unrelated_facts) :-
    apply_instance(instance(travel,
                            travel(tech1, depot, site_a),
                            [tech_at(tech1, site_a)],
                            [tech_at(tech1, depot)]),
                   [ticket_open(inc7),
                    link(depot, site_a),
                    tech_at(tech1, depot)],
                   Next),
    assertion(memberchk(ticket_open(inc7), Next)),
    assertion(memberchk(link(depot, site_a), Next)),
    assertion(memberchk(tech_at(tech1, site_a), Next)),
    assertion(\+ memberchk(tech_at(tech1, depot), Next)).

test(unsafe_unbound_effect_is_rejected,
     [error(instantiation_error)]) :-
    Schema = schema(unsafe,
                    reveal(Value),
                    [ticket_open(inc7)],
                    [revealed(Value)],
                    []),
    applicable(Schema,
               [ticket_open(inc7)],
               _).

test(field_service_plan_has_concrete_provenance_steps) :-
    field_service_schemas(Schemas),
    field_service_initial_state(Start),
    field_service_goal(Goal),
    breadth_first_plan(
        Schemas,
        Start,
        Goal,
        found(plan(
            [ step(pick_part, pick_up(tech1, psu42, depot)),
              step(travel, travel(tech1, depot, site_a)),
              step(replace_psu,
                   replace_psu(tech1, node7, psu42, psu_old))
            ],
            States)),
        Trace),
    assertion(States = [_, _, _, Final]),
    assertion(memberchk(restored(node7), Final)),
    assertion(memberchk(installed(node7, psu42), Final)),
    assertion(\+ memberchk(failed(node7), Final)),
    assertion(\+ memberchk(installed(node7, psu_old), Final)),
    maplist(state_keeps_ticket, States),
    assertion(Trace = [expanded(_, 0)|_]).

test(start_already_satisfies_goal_has_zero_step_plan) :-
    field_service_schemas(Schemas),
    field_service_initial_state(Start),
    breadth_first_plan(Schemas,
                       Start,
                       [ticket_open(inc7)],
                       found(plan([], [CanonicalStart])),
                       [expanded(CanonicalStart, 0)]),
    canonical_state(Start, CanonicalStart).

test(impossible_goal_exhausts_finite_domain) :-
    field_service_schemas(Schemas),
    field_service_initial_state(Start),
    impossible_field_service_goal(Goal),
    breadth_first_plan(Schemas,
                       Start,
                       Goal,
                       exhausted([restored(node999)]),
                       Trace),
    assertion(Trace \== []).

test(goal_satisfaction_is_set_based) :-
    goal_satisfied([restored(node7), ticket_open(inc7)],
                   [ticket_open(inc7),
                    restored(node7),
                    installed(node7, psu42)]).

state_keeps_ticket(State) :-
    memberchk(ticket_open(inc7), State).

:- end_tests(relational_planner).
