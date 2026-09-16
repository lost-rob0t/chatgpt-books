-module(pmsg_failure_lab).

-export([
    linked_crash/2,
    trapped_link_crash/2,
    monitored_crash/2,
    unlinked_crash/2,
    kill_trapper/1
]).

linked_crash(Reason, Timeout) when is_integer(Timeout), Timeout >= 0 ->
    Observer = self(),
    Ref = make_ref(),
    Controller = spawn(fun() -> linked_controller(Observer, Ref) end),
    Mon = erlang:monitor(process, Controller),
    receive
        {ready, Ref, Controller, Worker} ->
            Controller ! {crash_worker, Ref, Reason},
            receive
                {'DOWN', Mon, process, Controller, Reason} ->
                    {ok, {controller_down, Reason, Worker}};
                {'DOWN', Mon, process, Controller, OtherReason} ->
                    {error, {unexpected_controller_reason, OtherReason}}
            after Timeout ->
                stop_and_flush(Controller, Mon),
                {error, timeout}
            end
    after Timeout ->
        stop_and_flush(Controller, Mon),
        {error, timeout}
    end.

trapped_link_crash(Reason, Timeout) when is_integer(Timeout), Timeout >= 0 ->
    Observer = self(),
    Ref = make_ref(),
    Controller = spawn(fun() -> trapping_controller(Observer, Ref) end),
    Mon = erlang:monitor(process, Controller),
    receive
        {ready, Ref, Controller, Worker} ->
            Controller ! {crash_worker, Ref, Reason},
            receive
                {trapped_exit, Ref, Worker, Reason} ->
                    Controller ! {finish, Ref},
                    erlang:demonitor(Mon, [flush]),
                    {ok, {exit_message, Reason}};
                {'DOWN', Mon, process, Controller, DownReason} ->
                    {error, {controller_down, DownReason}}
            after Timeout ->
                stop_and_flush(Controller, Mon),
                {error, timeout}
            end
    after Timeout ->
        stop_and_flush(Controller, Mon),
        {error, timeout}
    end.

monitored_crash(Reason, Timeout) when is_integer(Timeout), Timeout >= 0 ->
    Worker = spawn(fun worker/0),
    Mon = erlang:monitor(process, Worker),
    Worker ! {crash, Reason},
    receive
        {'DOWN', Mon, process, Worker, Reason} ->
            {ok, {down, Reason}};
        {'DOWN', Mon, process, Worker, OtherReason} ->
            {error, {unexpected_worker_reason, OtherReason}}
    after Timeout ->
        stop_and_flush(Worker, Mon),
        {error, timeout}
    end.

unlinked_crash(Reason, Timeout) when is_integer(Timeout), Timeout >= 0 ->
    Observer = self(),
    Ref = make_ref(),
    Controller = spawn(fun() -> unlinking_controller(Observer, Ref) end),
    Mon = erlang:monitor(process, Controller),
    receive
        {ready_unlinked, Ref, Controller, Worker} ->
            Controller ! {crash_worker, Ref, Reason},
            receive
                {survived_unlinked_crash, Ref, Worker, Reason} ->
                    Controller ! {finish, Ref},
                    erlang:demonitor(Mon, [flush]),
                    {ok, {controller_survived, Reason}};
                {'DOWN', Mon, process, Controller, DownReason} ->
                    {error, {controller_down, DownReason}}
            after Timeout ->
                stop_and_flush(Controller, Mon),
                {error, timeout}
            end
    after Timeout ->
        stop_and_flush(Controller, Mon),
        {error, timeout}
    end.

kill_trapper(Timeout) when is_integer(Timeout), Timeout >= 0 ->
    Observer = self(),
    Ref = make_ref(),
    Trapper = spawn(fun() ->
        process_flag(trap_exit, true),
        Observer ! {trapper_ready, Ref, self()},
        receive
            stop -> ok
        end
    end),
    Mon = erlang:monitor(process, Trapper),
    receive
        {trapper_ready, Ref, Trapper} ->
            erlang:exit_signal(Trapper, kill),
            receive
                {'DOWN', Mon, process, Trapper, killed} ->
                    {ok, killed};
                {'DOWN', Mon, process, Trapper, OtherReason} ->
                    {error, {unexpected_reason, OtherReason}}
            after Timeout ->
                stop_and_flush(Trapper, Mon),
                {error, timeout}
            end
    after Timeout ->
        stop_and_flush(Trapper, Mon),
        {error, timeout}
    end.

linked_controller(Observer, Ref) ->
    Worker = spawn_link(fun worker/0),
    Observer ! {ready, Ref, self(), Worker},
    receive
        {crash_worker, Ref, Reason} ->
            Worker ! {crash, Reason},
            receive
                stop -> ok
            end
    end.

trapping_controller(Observer, Ref) ->
    process_flag(trap_exit, true),
    Worker = spawn_link(fun worker/0),
    Observer ! {ready, Ref, self(), Worker},
    receive
        {crash_worker, Ref, Reason} ->
            Worker ! {crash, Reason},
            receive
                {'EXIT', Worker, Reason} ->
                    Observer ! {trapped_exit, Ref, Worker, Reason},
                    receive
                        {finish, Ref} -> ok
                    end
            end
    end.

unlinking_controller(Observer, Ref) ->
    Worker = spawn_link(fun worker/0),
    true = unlink(Worker),
    WorkerMon = erlang:monitor(process, Worker),
    Observer ! {ready_unlinked, Ref, self(), Worker},
    receive
        {crash_worker, Ref, Reason} ->
            Worker ! {crash, Reason},
            receive
                {'DOWN', WorkerMon, process, Worker, Reason} ->
                    Observer ! {survived_unlinked_crash, Ref, Worker, Reason},
                    receive
                        {finish, Ref} -> ok
                    end
            end
    end.

worker() ->
    receive
        {crash, Reason} ->
            exit(Reason);
        stop ->
            ok
    end.

stop_and_flush(Pid, Mon) ->
    erlang:exit_signal(Pid, kill),
    erlang:demonitor(Mon, [flush]),
    ok.
