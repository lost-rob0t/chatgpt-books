-module(otp_worker_tests).

-include_lib("eunit/include/eunit.hrl").

publish_and_history_test() ->
    {ok, Pid} = otp_worker:start(),
    try
        ?assertEqual({ok, 1}, otp_worker:publish(Pid, <<"ops">>, <<"first">>)),
        ?assertEqual({ok, 2}, otp_worker:publish(Pid, <<"ops">>, <<"second">>)),
        ?assertEqual(
            {ok, [#{id => 1, payload => <<"first">>}, #{id => 2, payload => <<"second">>}]},
            otp_worker:history(Pid, <<"ops">>)
        )
    after
        stop_worker(Pid)
    end.

cast_then_call_observes_same_sender_order_test() ->
    {ok, Pid} = otp_worker:start(),
    try
        ok = otp_worker:publish_async(Pid, <<"order">>, <<"cast-first">>),
        ?assertEqual(
            {ok, [#{id => 1, payload => <<"cast-first">>}]},
            otp_worker:history(Pid, <<"order">>)
        )
    after
        stop_worker(Pid)
    end.

call_timeout_exits_without_late_reply_pollution_test() ->
    {ok, Pid} = otp_worker:start(),
    Parent = self(),
    Ref = make_ref(),
    Client = spawn(fun() -> timeout_client(Parent, Ref, Pid) end),
    Mon = erlang:monitor(process, Client),
    receive
        {timeout_result, Ref, timeout_exit} -> ok
    after 1000 ->
        ?assert(false)
    end,
    receive
        {mailbox_after_late_server_reply, Ref, []} -> ok;
        {mailbox_after_late_server_reply, Ref, Messages} ->
            ?assertEqual([], Messages)
    after 1000 ->
        ?assert(false)
    end,
    receive
        {'DOWN', Mon, process, Client, normal} -> ok
    after 1000 ->
        ?assert(false)
    end,
    stop_worker(Pid).

sys_get_state_exposes_callback_state_test() ->
    {ok, Pid} = otp_worker:start(),
    try
        ?assertEqual({ok, 1}, otp_worker:publish(Pid, <<"state">>, <<"visible">>)),
        State = sys:get_state(Pid),
        ?assertEqual(2, maps:get(next_id, State)),
        Messages = maps:get(messages, State),
        ?assertEqual(
            [#{id => 1, payload => <<"visible">>}],
            maps:get(<<"state">>, Messages)
        )
    after
        stop_worker(Pid)
    end.

supervisor_restarts_crashed_worker_and_state_resets_test() ->
    {ok, SupPid} = otp_worker_sup:start_link(),
    unlink(SupPid),
    try
        Worker1 = await_registered_worker(undefined, 1000),
        ?assertEqual({ok, 1}, otp_worker:publish(otp_worker, <<"ephemeral">>, <<"before">>)),
        Mon = erlang:monitor(process, Worker1),
        expect_exit(fun() -> otp_worker:crash(otp_worker, boom) end),
        receive
            {'DOWN', Mon, process, Worker1, boom} -> ok
        after 1000 ->
            ?assert(false)
        end,
        Worker2 = await_registered_worker(Worker1, 1000),
        ?assert(Worker1 =/= Worker2),
        ?assertEqual({ok, []}, otp_worker:history(otp_worker, <<"ephemeral">>))
    after
        stop_supervisor()
    end.

restart_intensity_escalates_test() ->
    {ok, SupPid} = otp_worker_sup:start_link(),
    unlink(SupPid),
    SupMon = erlang:monitor(process, SupPid),
    Worker1 = await_registered_worker(undefined, 1000),
    Worker2 = crash_and_await_replacement(Worker1, one),
    Worker3 = crash_and_await_replacement(Worker2, two),
    crash_without_waiting_for_replacement(Worker3, three),
    receive
        {'DOWN', SupMon, process, SupPid, shutdown} -> ok
    after 1000 ->
        ?assert(false)
    end,
    ?assertEqual(undefined, whereis(otp_worker)).

timeout_client(Parent, Ref, Server) ->
    Result =
        try otp_worker:delayed_echo(Server, 60, late, 5) of
            _Unexpected -> unexpected_reply
        catch
            exit:{timeout, {gen_server, call, _}} -> timeout_exit
        end,
    Parent ! {timeout_result, Ref, Result},
    _StateBarrier = sys:get_state(Server),
    {messages, Messages} = process_info(self(), messages),
    Parent ! {mailbox_after_late_server_reply, Ref, Messages}.

crash_and_await_replacement(Worker, Reason) ->
    crash_without_waiting_for_replacement(Worker, Reason),
    await_registered_worker(Worker, 1000).

crash_without_waiting_for_replacement(Worker, Reason) ->
    Mon = erlang:monitor(process, Worker),
    expect_exit(fun() -> otp_worker:crash(otp_worker, Reason) end),
    receive
        {'DOWN', Mon, process, Worker, Reason} -> ok
    after 1000 ->
        ?assert(false)
    end.

expect_exit(Fun) ->
    try Fun() of
        Unexpected ->
            ?assertEqual(expected_exit, {unexpected_return, Unexpected})
    catch
        exit:_Reason ->
            ok
    end.

await_registered_worker(Previous, Timeout) ->
    Deadline = erlang:monotonic_time(millisecond) + Timeout,
    await_registered_worker_until(Previous, Deadline).

await_registered_worker_until(Previous, Deadline) ->
    case whereis(otp_worker) of
        Pid when is_pid(Pid), Pid =/= Previous ->
            Pid;
        _ ->
            case erlang:monotonic_time(millisecond) >= Deadline of
                true ->
                    ?assert(false);
                false ->
                    receive after 1 -> ok end,
                    await_registered_worker_until(Previous, Deadline)
            end
    end.

stop_worker(Pid) ->
    case erlang:is_process_alive(Pid) of
        true -> otp_worker:stop(Pid);
        false -> ok
    end.

stop_supervisor() ->
    case whereis(otp_worker_sup) of
        undefined -> ok;
        _Pid -> otp_worker_sup:stop()
    end.
