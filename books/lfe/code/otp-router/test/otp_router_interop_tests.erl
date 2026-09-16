-module(otp_router_interop_tests).

-export([run/0]).

run() ->
    ok = direct_smoke(),
    ok = supervised_restart(),
    ok = restart_intensity(),
    ok.

direct_smoke() ->
    Rules = [{'when-level', critical, pager}],
    Event = {event, critical, edge, <<"disk full">>},
    {ok, Pid} = 'otp-router':start_link(Rules),
    {ok, pager} = gen_server:call('otp-router', {route, Event}, 1000),
    Rules = sys:get_state('otp-router'),
    ok = sys:suspend('otp-router'),
    TimeoutResult = catch gen_server:call('otp-router', 'get-rules', 20),
    case TimeoutResult of
        {'EXIT', {timeout, _}} -> ok;
        Other -> erlang:error({unexpected_gen_server_timeout_result, Other})
    end,
    ok = sys:resume('otp-router'),
    true = is_process_alive(Pid),
    ok = gen_server:stop('otp-router'),
    ok.

supervised_restart() ->
    Rules = [{'when-level', critical, pager}],
    Event = {event, critical, edge, <<"disk full">>},
    {ok, Sup} = 'otp-router-sup':start_link(Rules),
    unlink(Sup),
    Old = whereis('otp-router'),
    {ok, replaced} = 'otp-router':'replace-rules'([{otherwise, sink}], 1000),
    {ok, sink} = 'otp-router':route(Event, 1000),
    DownRef = erlang:monitor(process, Old),
    ok = 'otp-router':crash(boom),
    receive
        {'DOWN', DownRef, process, Old, boom} -> ok
    after 1000 ->
        erlang:error({worker_did_not_crash, Old})
    end,
    New = wait_for_replacement(Old, 100),
    true = is_process_alive(New),
    {ok, pager} = 'otp-router':route(Event, 1000),
    ok = gen_server:stop(Sup),
    ok.

restart_intensity() ->
    Rules = [{'when-level', critical, pager}],
    {ok, Sup} = 'otp-router-sup':start_link(Rules, 1, 60),
    unlink(Sup),
    SupRef = erlang:monitor(process, Sup),
    First = whereis('otp-router'),
    FirstRef = erlang:monitor(process, First),
    ok = 'otp-router':crash(first_boom),
    receive
        {'DOWN', FirstRef, process, First, first_boom} -> ok
    after 1000 ->
        erlang:error({first_worker_crash_not_observed, First})
    end,
    Second = wait_for_replacement(First, 100),
    SecondRef = erlang:monitor(process, Second),
    ok = 'otp-router':crash(second_boom),
    receive
        {'DOWN', SecondRef, process, Second, second_boom} -> ok
    after 1000 ->
        erlang:error({second_worker_crash_not_observed, Second})
    end,
    receive
        {'DOWN', SupRef, process, Sup, shutdown} -> ok;
        {'DOWN', SupRef, process, Sup, OtherReason} ->
            erlang:error({unexpected_supervisor_shutdown_reason, OtherReason})
    after 1000 ->
        erlang:error({restart_intensity_did_not_shutdown_supervisor, Sup})
    end.

wait_for_replacement(_OldPid, 0) ->
    erlang:error(restart_timeout);
wait_for_replacement(OldPid, Attempts) ->
    case whereis('otp-router') of
        Pid when is_pid(Pid), Pid =/= OldPid -> Pid;
        _ ->
            timer:sleep(10),
            wait_for_replacement(OldPid, Attempts - 1)
    end.
