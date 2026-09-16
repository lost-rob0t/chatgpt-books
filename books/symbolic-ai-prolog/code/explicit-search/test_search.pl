:- begin_tests(explicit_search).

:- use_module(search).
:- use_module(recovery_graph).

test(start_is_goal_has_zero_action_path) :-
    recovery_graph(Graph),
    breadth_first(Graph,
                  incident_open,
                  incident_open,
                  found(path([], [incident_open])),
                  [expanded(incident_open, 0)]).

test(depth_first_follows_first_transition_branch) :-
    recovery_graph(Graph),
    depth_first(Graph,
                incident_open,
                healthy,
                found(path([inspect_app,
                            restart_app_early,
                            check_broker_after_app,
                            start_broker,
                            restart_app],
                           [incident_open,
                            app_down,
                            app_waiting_for_broker,
                            broker_down,
                            broker_up,
                            healthy])),
                Trace),
    assertion(Trace == [expanded(incident_open, 0),
                        expanded(app_down, 1),
                        expanded(app_waiting_for_broker, 2),
                        expanded(broker_down, 3),
                        expanded(broker_up, 4),
                        expanded(healthy, 5)]).

test(breadth_first_finds_fewer_edge_path_on_fixture) :-
    recovery_graph(Graph),
    breadth_first(Graph,
                  incident_open,
                  healthy,
                  found(path([inspect_broker,
                              start_broker,
                              restart_app],
                             [incident_open,
                              broker_down,
                              broker_up,
                              healthy])),
                  _).

test(reordering_transitions_changes_depth_first_path) :-
    direct_first_recovery_graph(Graph),
    depth_first(Graph,
                incident_open,
                healthy,
                found(path([inspect_broker,
                            start_broker,
                            restart_app],
                           [incident_open,
                            broker_down,
                            broker_up,
                            healthy])),
                _).

test(cycles_terminate_with_explicit_exhaustion) :-
    recovery_graph(Graph),
    depth_first(Graph,
                incident_open,
                database_restored,
                exhausted(database_restored),
                Trace),
    assertion(Trace == [expanded(incident_open, 0),
                        expanded(app_down, 1),
                        expanded(app_waiting_for_broker, 2),
                        expanded(broker_down, 3),
                        expanded(broker_up, 4),
                        expanded(healthy, 5)]).

test(duplicate_frontier_state_expands_once) :-
    recovery_graph(Graph),
    breadth_first(Graph,
                  incident_open,
                  database_restored,
                  exhausted(database_restored),
                  Trace),
    findall(Depth,
            member(expanded(broker_down, Depth), Trace),
            BrokerDepths),
    assertion(BrokerDepths == [1]).

test(dfs_and_bfs_expose_different_expansion_order) :-
    recovery_graph(Graph),
    depth_first(Graph, incident_open, healthy, _, DfsTrace),
    breadth_first(Graph, incident_open, healthy, _, BfsTrace),
    assertion(DfsTrace == [expanded(incident_open, 0),
                           expanded(app_down, 1),
                           expanded(app_waiting_for_broker, 2),
                           expanded(broker_down, 3),
                           expanded(broker_up, 4),
                           expanded(healthy, 5)]),
    assertion(BfsTrace == [expanded(incident_open, 0),
                           expanded(app_down, 1),
                           expanded(broker_down, 1),
                           expanded(app_waiting_for_broker, 2),
                           expanded(broker_up, 2),
                           expanded(healthy, 3)]).

test(nonground_start_is_rejected,
     [error(instantiation_error)]) :-
    recovery_graph(Graph),
    depth_first(Graph, _, healthy, _, _).

test(malformed_transition_is_rejected,
     [error(type_error(edge_transition, broken_transition))]) :-
    depth_first([broken_transition],
                incident_open,
                healthy,
                _,
                _).

:- end_tests(explicit_search).
