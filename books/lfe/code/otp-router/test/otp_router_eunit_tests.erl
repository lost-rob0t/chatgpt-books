-module(otp_router_eunit_tests).

-include_lib("eunit/include/eunit.hrl").

router_contracts_test_() ->
    {foreach,
     fun setup_router/0,
     fun cleanup_router/1,
     [fun(State) -> ?_test(route_contract(State)) end,
      fun(State) -> ?_test(state_transition_contract(State)) end,
      fun(State) -> ?_test(domain_error_contract(State)) end]}.

setup_router() ->
    cleanup_registered_router(),
    Rules = [{'when-level', critical, pager}],
    Event = {event, critical, edge, <<"disk full">>},
    {ok, Pid} = 'otp-router':start_link(Rules),
    unlink(Pid),
    #{pid => Pid, rules => Rules, event => Event}.

cleanup_router(_State) ->
    cleanup_registered_router().

cleanup_registered_router() ->
    case whereis('otp-router') of
        undefined ->
            ok;
        Pid when is_pid(Pid) ->
            _ = catch gen_server:stop(Pid),
            wait_until_unregistered(100)
    end.

wait_until_unregistered(0) ->
    erlang:error(router_cleanup_timeout);
wait_until_unregistered(Attempts) ->
    case whereis('otp-router') of
        undefined -> ok;
        _ ->
            timer:sleep(10),
            wait_until_unregistered(Attempts - 1)
    end.

route_contract(State) ->
    Event = maps:get(event, State),
    Rules = maps:get(rules, State),
    ?assertEqual({ok, pager}, 'otp-router':route(Event, 1000)),
    ?assertEqual(Rules, sys:get_state('otp-router')).

state_transition_contract(State) ->
    Event = maps:get(event, State),
    NewRules = [{otherwise, sink}],
    ?assertEqual({ok, replaced},
                 'otp-router':'replace-rules'(NewRules, 1000)),
    ?assertEqual({ok, NewRules}, 'otp-router':'get-rules'(1000)),
    ?assertEqual({ok, sink}, 'otp-router':route(Event, 1000)).

domain_error_contract(_State) ->
    ?assertEqual({error, {'bad-request', wat}},
                 'otp-router':request(wat, 1000)).
