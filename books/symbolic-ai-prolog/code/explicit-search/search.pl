:- module(explicit_search,
          [ depth_first/5,
            breadth_first/5
          ]).

:- use_module(library(error), [must_be/2]).
:- use_module(library(ordsets), [ord_add_element/3, ord_memberchk/2]).

%% depth_first(+Transitions, +Start, +Goal, -Result, -Trace) is det.
%% breadth_first(+Transitions, +Start, +Goal, -Result, -Trace) is det.
%
% Search one finite, ground transition graph represented as edge(Action, From,
% To) terms.  Result is either found(path(Actions, States)) or exhausted(Goal).
% Trace records expanded(State, Depth) events in expansion order.  Duplicate
% frontier entries are skipped after the state has entered the closed set.
depth_first(Transitions, Start, Goal, Result, Trace) :-
    graph_search(dfs, Transitions, Start, Goal, Result, Trace).

breadth_first(Transitions, Start, Goal, Result, Trace) :-
    graph_search(bfs, Transitions, Start, Goal, Result, Trace).

graph_search(Strategy, Transitions, Start, Goal, Result, Trace) :-
    validate_search_input(Transitions, Start, Goal),
    Initial = node(Start, [], [Start], 0),
    search_loop(Strategy,
                Transitions,
                Goal,
                [Initial],
                [],
                Result,
                [],
                ReverseTrace),
    reverse(ReverseTrace, Trace).

search_loop(_, _, Goal, [], _, exhausted(Goal), Trace, Trace).
search_loop(Strategy,
            Transitions,
            Goal,
            [node(State, ReverseActions, ReverseStates, Depth)|Rest],
            Closed0,
            Result,
            Trace0,
            Trace) :-
    (   ord_memberchk(State, Closed0)
    ->  search_loop(Strategy,
                    Transitions,
                    Goal,
                    Rest,
                    Closed0,
                    Result,
                    Trace0,
                    Trace)
    ;   Trace1 = [expanded(State, Depth)|Trace0],
        (   State == Goal
        ->  reverse(ReverseActions, Actions),
            reverse(ReverseStates, States),
            Result = found(path(Actions, States)),
            Trace = Trace1
        ;   ord_add_element(Closed0, State, Closed1),
            successor_nodes(Transitions,
                            State,
                            ReverseActions,
                            ReverseStates,
                            Depth,
                            Closed1,
                            Children),
            next_frontier(Strategy, Children, Rest, Frontier),
            search_loop(Strategy,
                        Transitions,
                        Goal,
                        Frontier,
                        Closed1,
                        Result,
                        Trace1,
                        Trace)
        )
    ).

successor_nodes(Transitions,
                State,
                ReverseActions,
                ReverseStates,
                Depth,
                Closed,
                Children) :-
    NextDepth is Depth + 1,
    findall(node(To,
                 [Action|ReverseActions],
                 [To|ReverseStates],
                 NextDepth),
            ( member(edge(Action, State, To), Transitions),
              \+ ord_memberchk(To, Closed)
            ),
            Children).

next_frontier(dfs, Children, Rest, Frontier) :-
    append(Children, Rest, Frontier).
next_frontier(bfs, Children, Rest, Frontier) :-
    append(Rest, Children, Frontier).

validate_search_input(Transitions, Start, Goal) :-
    must_be(list, Transitions),
    require_ground(search_start, Start),
    require_ground(search_goal, Goal),
    maplist(validate_transition, Transitions).

validate_transition(edge(Action, From, To)) :-
    !,
    require_ground(transition_action, Action),
    require_ground(transition_from, From),
    require_ground(transition_to, To).
validate_transition(Term) :-
    throw(error(type_error(edge_transition, Term),
                context(explicit_search,
                        'Transitions must be edge(Action, From, To) terms'))).

require_ground(_, Term) :-
    ground(Term),
    !.
require_ground(Label, _) :-
    throw(error(instantiation_error,
                context(explicit_search,
                        Label))).
