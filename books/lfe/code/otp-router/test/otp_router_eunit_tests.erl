-module(otp_router_eunit_tests).

-include_lib("eunit/include/eunit.hrl").

router_contracts_test_() ->
    {foreach,
     fun setup_router/0,
     fun cleanup_router/1,
     [fun(State) -> ?_test(route_contract(State)) end,
      fun(State) -> ?_test(state_transition_contract(State)) end,
      fun(State) -> ?_test(domain_error_contract(State)) end]}.

fixture_rejects_ambient_registration_test() ->
    Dummy = spawn(fun dummy_loop/0),
    true = register('otp-router', Dummy),
    try
        ?assertError({router_name_in_use, Dummy}, setup_router()),
        ?assertEqual(Dummy, whereis('otp-router')),
        ?assert(is_process_alive(Dummy))
    after
        release_dummy_registration(Dummy)
    end.

fixture_cleanup_refuses_foreign_owner_test() ->
    State = setup_router(),
    OwnedPid = maps:get(pid, State),
    true = unregister('otp-router'),
    Dummy = spawn(fun dummy_loop/0),
    true = register('otp-router', Dummy),
    try
        ?assertError({router_registration_ownership_changed, OwnedPid, Dummy},
                     cleanup_router(State)),
        ?assertEqual(Dummy, whereis('otp-router')),
        ?assert(is_process_alive(Dummy)),
        ?assert(not is_process_alive(OwnedPid))
    after
        release_dummy_registration(Dummy),
        stop_owned_router_if_alive(OwnedPid)
    end.

setup_router() ->
    ensure_router_name_available(),
    Rules = [{'when-level', critical, pager}],
    Event = {event, critical, edge, <<"disk full">>},
    {ok, Pid} = 'otp-router':start_link(Rules),
    unlink(Pid),
    #{pid => Pid, rules => Rules, event => Event}.

cleanup_router(#{pid := Pid}) ->
    stop_owned_router_if_alive(Pid),
    wait_until_registration_released(Pid, 100).

ensure_router_name_available() ->
    case whereis('otp-router') of
        undefined -> ok;
        ExistingPid when is_pid(ExistingPid) ->
            erlang:error({router_name_in_use, ExistingPid})
    end.

stop_owned_router_if_alive(Pid) ->
    case is_process_alive(Pid) of
        false -> ok;
        true ->
            case catch gen_server:stop(Pid) of
                ok -> ok;
                {'EXIT', {noproc, _}} -> ok;
                {'EXIT', noproc} -> ok;
                {'EXIT', Reason} -> erlang:error({router_cleanup_failed, Pid, Reason})
            end
    end.

wait_until_registration_released(_OwnedPid, 0) ->
    erlang:error(router_cleanup_timeout);
wait_until_registration_released(OwnedPid, Attempts) ->
    case whereis('otp-router') of
        undefined ->
            ok;
        OwnedPid ->
            timer:sleep(10),
            wait_until_registration_released(OwnedPid, Attempts - 1);
        OtherPid when is_pid(OtherPid) ->
            erlang:error({router_registration_ownership_changed,
                          OwnedPid,
                          OtherPid})
    end.

release_dummy_registration(Dummy) ->
    case whereis('otp-router') of
        Dummy -> unregister('otp-router');
        _ -> ok
    end,
    Dummy ! stop,
    ok.

dummy_loop() ->
    receive
        stop -> ok
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
