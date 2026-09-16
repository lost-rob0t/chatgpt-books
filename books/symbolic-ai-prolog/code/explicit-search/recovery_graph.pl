:- module(recovery_graph,
          [ recovery_graph/1,
            direct_first_recovery_graph/1
          ]).

%% recovery_graph(-Transitions) is det.
%
% A finite operations/recovery graph with a deliberately longer first branch,
% a duplicate route to broker_down, and cycles back toward already-seen states.
% The graph is teaching data, not a model of a particular production system.
recovery_graph([
    edge(inspect_app,
         incident_open,
         app_down),
    edge(inspect_broker,
         incident_open,
         broker_down),
    edge(probe_broker_again,
         incident_open,
         broker_down),
    edge(restart_app_early,
         app_down,
         app_waiting_for_broker),
    edge(check_broker_after_app,
         app_waiting_for_broker,
         broker_down),
    edge(retry_app,
         app_waiting_for_broker,
         app_down),
    edge(start_broker,
         broker_down,
         broker_up),
    edge(restart_app,
         broker_up,
         healthy),
    edge(recheck_app,
         broker_up,
         app_down)
]).

%% direct_first_recovery_graph(-Transitions) is det.
%
% Same graph, but the broker inspection transition is ordered before the app
% inspection transition so depth-first search commits to a different first
% path.  Breadth-first search still uses the same unit-edge state space.
direct_first_recovery_graph([
    edge(inspect_broker,
         incident_open,
         broker_down),
    edge(inspect_app,
         incident_open,
         app_down),
    edge(probe_broker_again,
         incident_open,
         broker_down),
    edge(restart_app_early,
         app_down,
         app_waiting_for_broker),
    edge(check_broker_after_app,
         app_waiting_for_broker,
         broker_down),
    edge(retry_app,
         app_waiting_for_broker,
         app_down),
    edge(start_broker,
         broker_down,
         broker_up),
    edge(restart_app,
         broker_up,
         healthy),
    edge(recheck_app,
         broker_up,
         app_down)
]).
