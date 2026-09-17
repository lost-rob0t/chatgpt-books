-module(job_processor_tests).

-include_lib("eunit/include/eunit.hrl").

bounded_admission_test() ->
    with_system(#{max_active => 1, max_queued => 1, max_attempts => 2},
                fun() ->
                    GateRef = make_ref(),
                    {ok, First} = job_processor:submit({gate, self(), GateRef, first}),
                    Worker = await_waiting(First, 1, GateRef),
                    {ok, Second} = job_processor:submit({echo, second}),
                    ?assertEqual({error, overloaded},
                                 job_processor:submit({echo, rejected})),
                    Stats0 = job_processor:stats(),
                    ?assertEqual(1, maps:get(active, Stats0)),
                    ?assertEqual(1, maps:get(queued, Stats0)),
                    ?assertEqual(1, maps:get(rejected, Stats0)),
                    Worker ! {release, GateRef},
                    ?assertEqual({ok, first}, await_result(First)),
                    ?assertEqual({ok, second}, await_result(Second)),
                    await_no_dynamic_children(),
                    Stats1 = job_processor:stats(),
                    ?assertEqual(2, maps:get(completed, Stats1)),
                    ?assertEqual(0, maps:get(active, Stats1)),
                    ?assertEqual(0, maps:get(queued, Stats1))
                end).

fifo_pending_order_test() ->
    with_system(#{max_active => 1, max_queued => 2, max_attempts => 2},
                fun() ->
                    GateRef = make_ref(),
                    {ok, First} = job_processor:submit({gate, self(), GateRef, first}),
                    Worker = await_waiting(First, 1, GateRef),
                    {ok, Second} = job_processor:submit({echo, second}),
                    {ok, Third} = job_processor:submit({echo, third}),
                    Worker ! {release, GateRef},
                    ?assertEqual({ok, first}, await_result(First)),
                    ?assertEqual({ok, second}, await_result(Second)),
                    ?assertEqual({ok, third}, await_result(Third))
                end).

crash_retry_succeeds_test() ->
    with_system(#{max_active => 1, max_queued => 1, max_attempts => 2},
                fun() ->
                    {ok, JobId} = job_processor:submit({crash_until, 1, recovered}),
                    ?assertEqual({ok, recovered}, await_result(JobId)),
                    Stats = job_processor:stats(),
                    ?assertEqual(1, maps:get(retried, Stats)),
                    ?assertEqual(1, maps:get(completed, Stats)),
                    ?assertEqual(0, maps:get(failed, Stats))
                end).

retry_budget_exhaustion_test() ->
    with_system(#{max_active => 1, max_queued => 1, max_attempts => 2},
                fun() ->
                    {ok, JobId} = job_processor:submit({crash_until, 99, never}),
                    ?assertEqual({error, {worker_exit, {deliberate_crash, 2}}},
                                 await_result(JobId)),
                    Stats = job_processor:stats(),
                    ?assertEqual(1, maps:get(retried, Stats)),
                    ?assertEqual(1, maps:get(failed, Stats)),
                    ?assertEqual(0, maps:get(completed, Stats))
                end).

queue_restart_loses_volatile_ledger_test() ->
    with_system(#{max_active => 1, max_queued => 1, max_attempts => 2},
                fun() ->
                    GateRef = make_ref(),
                    {ok, JobId} = job_processor:submit({gate, self(), GateRef, orphaned}),
                    Worker = await_waiting(JobId, 1, GateRef),
                    OldProcessor = whereis(job_processor),
                    Monitor = erlang:monitor(process, OldProcessor),
                    exit(OldProcessor, kill),
                    receive
                        {'DOWN', Monitor, process, OldProcessor, killed} -> ok
                    after 3000 ->
                        error(queue_process_did_not_die)
                    end,
                    NewProcessor = await_new_processor(OldProcessor, 3000),
                    ?assert(is_pid(NewProcessor)),
                    Stats = job_processor:stats(),
                    ?assertEqual(0, maps:get(active, Stats)),
                    ?assertEqual(0, maps:get(queued, Stats)),
                    Worker ! {release, GateRef},
                    receive
                        {job_result, JobId, _Unexpected} ->
                            error(restarted_queue_recovered_unpersisted_job)
                    after 1200 ->
                        ok
                    end,
                    await_no_dynamic_children()
                end).

with_system(Opts, Fun) ->
    cleanup_existing(),
    {ok, Sup} = job_processor_sup:start_link(Opts),
    unlink(Sup),
    try
        Fun()
    after
        stop_supervisor(Sup),
        cleanup_mailbox()
    end.

stop_supervisor(Sup) ->
    case is_process_alive(Sup) of
        true ->
            try supervisor:stop(Sup) of
                ok -> ok
            catch
                exit:_StopReason -> ok
            end;
        false ->
            ok
    end,
    await_name_gone(job_processor_sup, 3000),
    await_name_gone(job_processor, 3000),
    await_name_gone(job_worker_sup, 3000).

cleanup_existing() ->
    case whereis(job_processor_sup) of
        undefined -> ok;
        Sup -> stop_supervisor(Sup)
    end.

await_waiting(JobId, Attempt, GateRef) ->
    receive
        {worker_waiting, JobId, Attempt, GateRef, Worker} -> Worker
    after 3000 ->
        error({worker_did_not_wait, JobId, Attempt})
    end.

await_result(JobId) ->
    receive
        {job_result, JobId, Result} -> Result
    after 5000 ->
        error({job_result_timeout, JobId})
    end.

await_new_processor(OldProcessor, Timeout) ->
    Deadline = erlang:monotonic_time(millisecond) + Timeout,
    await_new_processor_loop(OldProcessor, Deadline).

await_new_processor_loop(OldProcessor, Deadline) ->
    case whereis(job_processor) of
        Pid when is_pid(Pid), Pid =/= OldProcessor -> Pid;
        _ ->
            case erlang:monotonic_time(millisecond) < Deadline of
                true ->
                    timer:sleep(10),
                    await_new_processor_loop(OldProcessor, Deadline);
                false ->
                    error(queue_process_was_not_restarted)
            end
    end.

await_no_dynamic_children() ->
    Deadline = erlang:monotonic_time(millisecond) + 3000,
    await_no_dynamic_children_loop(Deadline).

await_no_dynamic_children_loop(Deadline) ->
    Counts = supervisor:count_children(job_worker_sup),
    Active = proplists:get_value(active, Counts),
    Specs = proplists:get_value(specs, Counts),
    case {Active, Specs} of
        {0, 0} -> ok;
        _ ->
            case erlang:monotonic_time(millisecond) < Deadline of
                true ->
                    timer:sleep(10),
                    await_no_dynamic_children_loop(Deadline);
                false ->
                    error({dynamic_children_remain, Counts})
            end
    end.

await_name_gone(Name, Timeout) ->
    Deadline = erlang:monotonic_time(millisecond) + Timeout,
    await_name_gone_loop(Name, Deadline).

await_name_gone_loop(Name, Deadline) ->
    case whereis(Name) of
        undefined -> ok;
        _Pid ->
            case erlang:monotonic_time(millisecond) < Deadline of
                true ->
                    timer:sleep(10),
                    await_name_gone_loop(Name, Deadline);
                false ->
                    error({registered_name_remains, Name})
            end
    end.

cleanup_mailbox() ->
    receive
        _Message -> cleanup_mailbox()
    after 0 ->
        ok
    end.
