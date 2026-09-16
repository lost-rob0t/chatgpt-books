-module(otp_worker_app_tests).

-include_lib("eunit/include/eunit.hrl").

application_resource_contract_test() ->
    cleanup_application(),
    ok = application:load(otp_worker_app),
    try
        ?assertEqual(
            {ok, [otp_worker_app, otp_worker_sup, otp_worker]},
            application:get_key(otp_worker_app, modules)
        ),
        ?assertEqual(
            {ok, [otp_worker_sup, otp_worker]},
            application:get_key(otp_worker_app, registered)
        ),
        ?assertEqual(
            {ok, [kernel, stdlib]},
            application:get_key(otp_worker_app, applications)
        ),
        ?assertEqual(
            {ok, {otp_worker_app, []}},
            application:get_key(otp_worker_app, mod)
        )
    after
        ok = application:unload(otp_worker_app)
    end.

application_start_owns_supervision_tree_test() ->
    start_application(),
    try
        SupPid = whereis(otp_worker_sup),
        WorkerPid = whereis(otp_worker),
        ?assert(is_pid(SupPid)),
        ?assert(is_pid(WorkerPid)),
        ?assertEqual({ok, otp_worker_app}, application:get_application(WorkerPid)),
        ?assert(
            lists:keymember(
                otp_worker_app,
                1,
                application:which_applications()
            )
        )
    after
        cleanup_application()
    end.

application_stop_terminates_owned_tree_test() ->
    start_application(),
    SupPid = whereis(otp_worker_sup),
    WorkerPid = whereis(otp_worker),
    SupMon = erlang:monitor(process, SupPid),
    WorkerMon = erlang:monitor(process, WorkerPid),
    ok = application:stop(otp_worker_app),
    await_down(SupMon, SupPid),
    await_down(WorkerMon, WorkerPid),
    ?assertEqual(undefined, whereis(otp_worker_sup)),
    ?assertEqual(undefined, whereis(otp_worker)),
    ok = application:unload(otp_worker_app).

application_restart_reinitializes_volatile_state_test() ->
    start_application(),
    Sup1 = whereis(otp_worker_sup),
    Worker1 = whereis(otp_worker),
    ?assertEqual(
        {ok, 1},
        otp_worker:publish(otp_worker, <<"restart">>, <<"before-stop">>)
    ),
    ok = application:stop(otp_worker_app),
    ?assertEqual(undefined, whereis(otp_worker_sup)),
    ?assertEqual(undefined, whereis(otp_worker)),
    ok = application:start(otp_worker_app),
    try
        Sup2 = whereis(otp_worker_sup),
        Worker2 = whereis(otp_worker),
        ?assert(is_pid(Sup2)),
        ?assert(is_pid(Worker2)),
        ?assert(Sup1 =/= Sup2),
        ?assert(Worker1 =/= Worker2),
        ?assertEqual(
            {ok, []},
            otp_worker:history(otp_worker, <<"restart">>)
        )
    after
        cleanup_application()
    end.

start_application() ->
    cleanup_application(),
    ok = application:load(otp_worker_app),
    ok = application:start(otp_worker_app).

cleanup_application() ->
    case lists:keymember(otp_worker_app, 1, application:which_applications()) of
        true ->
            ok = application:stop(otp_worker_app);
        false ->
            stop_stray_supervisor()
    end,
    case lists:keymember(otp_worker_app, 1, application:loaded_applications()) of
        true ->
            ok = application:unload(otp_worker_app);
        false ->
            ok
    end.

stop_stray_supervisor() ->
    case whereis(otp_worker_sup) of
        undefined ->
            ok;
        _Pid ->
            otp_worker_sup:stop()
    end.

await_down(Mon, Pid) ->
    receive
        {'DOWN', Mon, process, Pid, _Reason} ->
            ok
    after 1000 ->
        ?assert(false)
    end.
