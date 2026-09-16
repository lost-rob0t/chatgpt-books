:- module(symbolic_meta_programs,
          [ incident_program/1,
            diagnostic_program/1
          ]).

%% incident_program(-Program) is det.
%
%  Synthetic rule-as-data knowledge base used throughout Project 1.  Rule
%  identifiers are stable provenance labels, not predicate names.
incident_program([
    rule(f_power_gateway, powered(gateway), true),
    rule(f_link_gateway_router, link(gateway, router), true),
    rule(f_link_router_cache, link(router, cache), true),
    rule(f_link_cache_database, link(cache, database), true),
    rule(f_symptom_temp, symptom(alpha, high_temp), true),
    rule(f_symptom_fan, symptom(alpha, fan_stopped), true),
    rule(r_risk_temp, risk(Host), symptom(Host, high_temp)),
    rule(r_risk_fan, risk(Host), symptom(Host, fan_stopped)),
    rule(r_reach_direct, reachable(From, To), link(From, To)),
    rule(r_reach_step,
         reachable(From, To),
         (link(From, Via), reachable(Via, To)))
]).

%% diagnostic_program(-Program) is det.
%
%  Intentionally hostile rules for the control/failure labs.  Do not merge
%  these into the ordinary incident program: their job is to make looping and
%  budget exhaustion observable on demand.
diagnostic_program([
    rule(r_loop, unstable(Node), unstable(Node)),
    rule(r_grow, grow(Term), grow(s(Term)))
]).
