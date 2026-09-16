-module(erlang_foundations_tests).

-include_lib("eunit/include/eunit.hrl").

classify_test() ->
    ?assertEqual(negative_integer, erlang_foundations:classify(-1)),
    ?assertEqual(non_negative_integer, erlang_foundations:classify(0)),
    ?assertEqual(empty_binary, erlang_foundations:classify(<<>>)),
    ?assertEqual(binary, erlang_foundations:classify(<<"beam">>)),
    ?assertEqual(list, erlang_foundations:classify([beam])).

sum_test() ->
    ?assertEqual(0, erlang_foundations:sum([])),
    ?assertEqual(10, erlang_foundations:sum([1, 2, 3, 4])).

normalize_command_test() ->
    ?assertEqual(
        {ok, {publish, <<"ops">>, <<"up">>}},
        erlang_foundations:normalize_command({publish, <<"ops">>, <<"up">>})
    ),
    ?assertMatch(
        {error, {invalid_command, _}},
        erlang_foundations:normalize_command({publish, ops, <<"up">>})
    ).

publish_and_history_test() ->
    Pid = pmsg_server:start(),
    ?assertEqual({ok, 1}, pmsg_server:publish(Pid, <<"ops">>, <<"first">>, 1000)),
    ?assertEqual({ok, 2}, pmsg_server:publish(Pid, <<"ops">>, <<"second">>, 1000)),
    ?assertEqual(
        {ok, [#{id => 1, payload => <<"first">>}, #{id => 2, payload => <<"second">>}]},
        pmsg_server:history(Pid, <<"ops">>, 1000)
    ),
    ?assertEqual(ok, pmsg_server:stop(Pid, 1000)).

selective_receive_preserves_unrelated_message_test() ->
    Pid = pmsg_server:start(),
    Noise = {noise, make_ref()},
    self() ! Noise,
    ?assertEqual({ok, []}, pmsg_server:history(Pid, <<"ops">>, 1000)),
    receive
        Noise -> ok
    after 0 ->
        ?assert(false)
    end,
    ?assertEqual(ok, pmsg_server:stop(Pid, 1000)).

same_sender_request_order_test() ->
    Pid = pmsg_server:start(),
    Ref1 = make_ref(),
    Ref2 = make_ref(),
    Pid ! {request, self(), Ref1, {publish, <<"order">>, <<"one">>}},
    Pid ! {request, self(), Ref2, {publish, <<"order">>, <<"two">>}},
    receive
        {reply, Ref1, {ok, 1}} -> ok
    after 1000 ->
        ?assert(false)
    end,
    receive
        {reply, Ref2, {ok, 2}} -> ok
    after 1000 ->
        ?assert(false)
    end,
    ?assertEqual(ok, pmsg_server:stop(Pid, 1000)).

timeout_is_not_cancellation_test() ->
    Pid = pmsg_server:start(),
    Ref = make_ref(),
    Pid ! {request, self(), Ref, {delay, 50, late}},
    receive
        {reply, Ref, _} ->
            ?assert(false)
    after 5 ->
        ok
    end,
    receive
        {reply, Ref, {ok, late}} ->
            ok
    after 1000 ->
        ?assert(false)
    end,
    ?assertEqual(ok, pmsg_server:stop(Pid, 1000)).

crash_is_observed_through_monitor_test() ->
    Pid = pmsg_server:start(),
    ?assertEqual({error, {server_down, boom}}, pmsg_server:inject_crash(Pid, boom)),
    ?assertEqual(false, erlang:is_process_alive(Pid)).

unknown_request_is_data_test() ->
    Pid = pmsg_server:start(),
    ?assertEqual(
        {error, {unknown_request, {wat, 42}}},
        pmsg_server:call(Pid, {wat, 42}, 1000)
    ),
    ?assertEqual(ok, pmsg_server:stop(Pid, 1000)).
